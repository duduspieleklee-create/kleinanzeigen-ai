#!/usr/bin/env bash
# Azure infrastructure setup for kleinanzeigen-ai
# Usage: export PG_PASS="YourStr0ng#Pass" && chmod +x infra/azure-setup.sh && ./infra/azure-setup.sh
set -euo pipefail

# ── Config — edit if you need different names/region ──────────────────────────
RG="kleinanzeigen-ai-rg"
LOCATION="westeurope"
ACR_NAME="kleinanzeigenai"        # globally unique, lowercase, no hyphens
PG_SERVER="kleinanzeigen-db"
PG_USER="kaadmin"
PG_PASS="${PG_PASS:?Export PG_PASS before running: export PG_PASS='YourStr0ng#Pass'}"
PG_DB="kleinanzeigen_ai"
REDIS_NAME="kleinanzeigen-redis"
CA_ENV="kleinanzeigen-env"
# ──────────────────────────────────────────────────────────────────────────────

echo "==> Registering resource providers (only needed once per subscription)..."
for NS in Microsoft.DBforPostgreSQL Microsoft.Cache Microsoft.App \
           Microsoft.OperationalInsights Microsoft.ContainerRegistry; do
  echo "    $NS"
  az provider register --namespace "$NS" --wait -o none
done

echo "==> Resource group..."
az group create --name "$RG" --location "$LOCATION" -o none

echo "==> Azure Container Registry..."
az acr create --resource-group "$RG" --name "$ACR_NAME" \
  --sku Basic --admin-enabled true -o none

echo "==> PostgreSQL Flexible Server (takes ~5 min)..."
az postgres flexible-server create \
  --resource-group "$RG" --name "$PG_SERVER" --location "$LOCATION" \
  --admin-user "$PG_USER" --admin-password "$PG_PASS" \
  --sku-name Standard_B1ms --tier Burstable --version 15 \
  --public-access 0.0.0.0 -o none

echo "==> PostgreSQL database..."
az postgres flexible-server db create \
  --resource-group "$RG" --server-name "$PG_SERVER" --name "$PG_DB" -o none

echo "==> Azure Cache for Redis (takes ~10 min)..."
az redis create \
  --resource-group "$RG" --name "$REDIS_NAME" --location "$LOCATION" \
  --sku Basic --vm-size c0 -o none

echo "==> Container Apps environment..."
az containerapp env create \
  --resource-group "$RG" --name "$CA_ENV" --location "$LOCATION" -o none

echo "==> Container Apps..."
ACR_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
ACR_PASS=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

for APP in api worker beat; do
  if [[ "$APP" == "api" ]]; then
    INGRESS_ARGS="--ingress external --target-port 8000"
  else
    INGRESS_ARGS="--ingress disabled"
  fi
  az containerapp create \
    --resource-group "$RG" \
    --environment "$CA_ENV" \
    --name "kleinanzeigen-$APP" \
    --image "$ACR_SERVER/kleinanzeigen-ai-$APP:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASS" \
    $INGRESS_ARGS --cpu 0.5 --memory 1.0Gi -o none
  echo "    ✓ kleinanzeigen-$APP"
done

# ── Collect output values ──────────────────────────────────────────────────────
PG_HOST="$PG_SERVER.postgres.database.azure.com"
REDIS_KEY=$(az redis list-keys --resource-group "$RG" --name "$REDIS_NAME" \
              --query primaryKey -o tsv)
ACR_USER=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
API_URL=$(az containerapp show --resource-group "$RG" --name "kleinanzeigen-api" \
            --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "<not yet available>")

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  All resources created. Add these to GitHub Secrets:"
echo "  Settings → Secrets and variables → Actions → New repository secret"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "ACR_LOGIN_SERVER     = $ACR_SERVER"
echo "ACR_USERNAME         = $ACR_USER"
echo "ACR_PASSWORD         = $ACR_PASS"
echo "DATABASE_URL         = postgresql://$PG_USER:$PG_PASS@$PG_HOST:5432/$PG_DB?sslmode=require"
echo "REDIS_URL            = rediss://:$REDIS_KEY@$REDIS_NAME.redis.cache.windows.net:6380/0"
echo ""
echo "Still needed (add manually):"
echo "SECRET_KEY           = \$(openssl rand -hex 32)"
echo "GOOGLE_CLIENT_ID     = <Google Cloud Console → APIs & Services → Credentials>"
echo "GOOGLE_CLIENT_SECRET = <same>"
echo "OCTOPUS_SERVER_URL   = <your Octopus Cloud URL>"
echo "OCTOPUS_API_KEY      = <Octopus → Profile → API Keys → New API Key>"
echo ""
echo "App URL: https://$API_URL"
echo "════════════════════════════════════════════════════════════"
