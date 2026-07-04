#!/usr/bin/env bash
# Google Cloud infrastructure setup for kleinanzeigen-ai
# Usage: gcloud config set project YOUR_PROJECT_ID
#        export PG_PASS="YourStr0ng#Pass" && chmod +x infra/gcp-setup.sh && ./infra/gcp-setup.sh
#
# This provisions the persistent, one-time infrastructure only (network,
# database, cache, registry, secrets, service accounts, CI identity). The
# Cloud Run services/job themselves are created on the first CI deploy via
# `gcloud run deploy` / `gcloud run jobs deploy`, which create-or-update —
# there's no separate "create the service" step like ECS requires.
set -euo pipefail

# ── Config — edit if you need different names/region ──────────────────────────
REGION="europe-north1"                # Hamina, Finland — closest GCP region to eu-north-1
NETWORK="kleinanzeigen-vpc"
CONNECTOR="kleinanzeigen-connector"
CONNECTOR_RANGE="10.8.0.0/28"
PSA_RANGE_NAME="kleinanzeigen-psa-range"
PSA_PREFIX_LENGTH="20"
SQL_INSTANCE="kleinanzeigen-db"
SQL_TIER="db-custom-1-3840"
SQL_USER="kaadmin"
SQL_DB="kleinanzeigen_ai"
PG_PASS="${PG_PASS:?Export PG_PASS before running: export PG_PASS='YourStr0ng#Pass'}"
REDIS_INSTANCE="kleinanzeigen-redis"
AR_REPO="kleinanzeigen-ai"
RUN_SA_NAME="kleinanzeigen-run-sa"
GHA_SA_NAME="kleinanzeigen-gha-deploy"
WIF_POOL="github-pool"
WIF_PROVIDER="github-provider"
GITHUB_REPO="duduspieleklee-create/kleinanzeigen-ai"
SECRET_PREFIX="kleinanzeigen"
# ──────────────────────────────────────────────────────────────────────────────

PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "No default project set. Run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUN_SA="${RUN_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
GHA_SA="${GHA_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> Enabling required APIs (takes a minute the first time)..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  >/dev/null

echo "==> VPC network..."
gcloud compute networks describe "$NETWORK" >/dev/null 2>&1 || \
  gcloud compute networks create "$NETWORK" --subnet-mode=custom >/dev/null

echo "==> Private Services Access range for Cloud SQL + Memorystore..."
gcloud compute addresses describe "$PSA_RANGE_NAME" --global >/dev/null 2>&1 || \
  gcloud compute addresses create "$PSA_RANGE_NAME" \
    --global --purpose=VPC_PEERING --prefix-length="$PSA_PREFIX_LENGTH" \
    --network="$NETWORK" >/dev/null

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges="$PSA_RANGE_NAME" \
  --network="$NETWORK" >/dev/null 2>&1 || true

echo "==> Serverless VPC Access connector (lets Cloud Run reach private IPs)..."
gcloud compute networks vpc-access connectors describe "$CONNECTOR" --region="$REGION" >/dev/null 2>&1 || \
  gcloud compute networks vpc-access connectors create "$CONNECTOR" \
    --region="$REGION" --network="$NETWORK" --range="$CONNECTOR_RANGE" >/dev/null
echo "    waiting for connector to become ready..."
while [[ "$(gcloud compute networks vpc-access connectors describe "$CONNECTOR" --region="$REGION" --format='value(state)')" != "READY" ]]; do
  sleep 5
done

echo "==> Artifact Registry (Docker repo)..."
gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker --location="$REGION" \
    --description="kleinanzeigen-ai container images" >/dev/null

echo "==> Cloud SQL for PostgreSQL, private IP only (takes ~5-10 min)..."
gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1 || \
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_15 \
    --tier="$SQL_TIER" \
    --region="$REGION" \
    --network="projects/$PROJECT_ID/global/networks/$NETWORK" \
    --no-assign-ip \
    --backup-start-time=03:00 \
    >/dev/null

gcloud sql databases describe "$SQL_DB" --instance="$SQL_INSTANCE" >/dev/null 2>&1 || \
  gcloud sql databases create "$SQL_DB" --instance="$SQL_INSTANCE" >/dev/null

gcloud sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$SQL_USER" || \
  gcloud sql users create "$SQL_USER" --instance="$SQL_INSTANCE" --password="$PG_PASS" >/dev/null

echo "==> Memorystore for Redis, private IP (takes ~5-10 min)..."
gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" >/dev/null 2>&1 || \
  gcloud redis instances create "$REDIS_INSTANCE" \
    --region="$REGION" --tier=basic --size=1 \
    --network="projects/$PROJECT_ID/global/networks/$NETWORK" \
    --connect-mode=private-service-access \
    --redis-version=redis_7_0 \
    >/dev/null
echo "    waiting for Redis to become ready..."
gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format='value(state)' | grep -qx READY \
  || (while [[ "$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format='value(state)')" != "READY" ]]; do sleep 10; done)

echo "==> Secret Manager placeholders..."
for NAME in DATABASE_URL REDIS_URL SECRET_KEY APP_USERNAME APP_PASSWORD ALLOWED_EMAILS \
            ADMIN_EMAILS SYSTEM_USER_ID VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY VAPID_EMAIL \
            GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET \
            STRIPE_PRICE_CORE STRIPE_PRICE_PRO PUBLIC_BASE_URL RESEND_API_KEY EMAIL_FROM; do
  SECRET_ID="${SECRET_PREFIX}-${NAME}"
  gcloud secrets describe "$SECRET_ID" >/dev/null 2>&1 || {
    gcloud secrets create "$SECRET_ID" --replication-policy=automatic >/dev/null
    printf 'CHANGE_ME' | gcloud secrets versions add "$SECRET_ID" --data-file=- >/dev/null
  }
done

echo "==> Cloud Run runtime service account..."
gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$RUN_SA_NAME" \
    --display-name="Cloud Run runtime for kleinanzeigen-ai" >/dev/null

for NAME in DATABASE_URL REDIS_URL SECRET_KEY APP_USERNAME APP_PASSWORD ALLOWED_EMAILS \
            ADMIN_EMAILS SYSTEM_USER_ID VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY VAPID_EMAIL \
            GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET \
            STRIPE_PRICE_CORE STRIPE_PRICE_PRO PUBLIC_BASE_URL RESEND_API_KEY EMAIL_FROM; do
  gcloud secrets add-iam-policy-binding "${SECRET_PREFIX}-${NAME}" \
    --member="serviceAccount:$RUN_SA" --role=roles/secretmanager.secretAccessor >/dev/null
done

echo "==> GitHub Actions Workload Identity Federation..."
gcloud iam workload-identity-pools describe "$WIF_POOL" --location=global >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create "$WIF_POOL" \
    --location=global --display-name="GitHub Actions" >/dev/null

gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER" \
  --location=global --workload-identity-pool="$WIF_POOL" >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
    --location=global --workload-identity-pool="$WIF_POOL" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="attribute.repository=='$GITHUB_REPO'" \
    >/dev/null

gcloud iam service-accounts describe "$GHA_SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$GHA_SA_NAME" \
    --display-name="GitHub Actions deploy identity" >/dev/null

gcloud iam service-accounts add-iam-policy-binding "$GHA_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/attribute.repository/$GITHUB_REPO" \
  >/dev/null

echo "==> Granting the GitHub Actions identity deploy permissions..."
for ROLE in roles/artifactregistry.writer roles/run.developer roles/secretmanager.admin; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$GHA_SA" --role="$ROLE" --condition=None >/dev/null
done
# Lets the deploy identity launch Cloud Run revisions running as the runtime SA.
gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" \
  --member="serviceAccount:$GHA_SA" --role=roles/iam.serviceAccountUser >/dev/null

# ── Collect output values ──────────────────────────────────────────────────────
SQL_PRIVATE_IP=$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(ipAddresses[0].ipAddress)')
REDIS_HOST=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format='value(host)')
SQL_CONNECTION_NAME=$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')
WIF_PROVIDER_RESOURCE="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/providers/$WIF_PROVIDER"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  All resources created. Add these to GitHub Secrets/Variables:"
echo "  Settings → Secrets and variables → Actions"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "GCP_WORKLOAD_IDENTITY_PROVIDER  (secret) = $WIF_PROVIDER_RESOURCE"
echo "GCP_SERVICE_ACCOUNT             (secret) = $GHA_SA"
echo "GCP_PROJECT_ID                  (variable) = $PROJECT_ID"
echo "GCP_REGION                      (variable) = $REGION"
echo ""
echo "Update these Secret Manager values (currently CHANGE_ME placeholders):"
echo "  printf '%s' \"postgresql://$SQL_USER:$PG_PASS@$SQL_PRIVATE_IP:5432/$SQL_DB\" | \\"
echo "    gcloud secrets versions add ${SECRET_PREFIX}-DATABASE_URL --data-file=-"
echo "  printf '%s' \"redis://$REDIS_HOST:6379/0\" | \\"
echo "    gcloud secrets versions add ${SECRET_PREFIX}-REDIS_URL --data-file=-"
echo "  ... and SECRET_KEY, GOOGLE_CLIENT_ID/SECRET, STRIPE_*, VAPID_*, RESEND_API_KEY, etc."
echo "  (same pattern: printf '%s' \"VALUE\" | gcloud secrets versions add ${SECRET_PREFIX}-NAME --data-file=-)"
echo ""
echo "Each secret update is picked up on the next deploy (the CI deploy job"
echo "always redeploys the Cloud Run revisions after syncing secrets)."
echo ""
echo "Cloud SQL connection name (for reference): $SQL_CONNECTION_NAME"
echo "Cloud Run services/job are created by the first CI run (see"
echo "  .github/workflows/build-and-push.yml) — nothing more to do here."
echo "════════════════════════════════════════════════════════════"
