# TODO — Before first deploy

---

## 1. Azure Prerequisites
Complete these steps in Azure before running Terraform or CI.

### 1.1 Provision infrastructure with Terraform
Run Terraform to create all Azure resources (see `docs/terraform.md`):
```bash
cd infrastructure/terraform/environments/dev
export TF_VAR_postgres_admin_password="your-strong-password"
terraform init -backend-config=../../backend-config.dev.conf
terraform apply -var-file=terraform.tfvars
```
This creates:
- Resource group `kleinanzeigen-ai-dev-rg`
- AKS cluster `kleinanzeigen-aks-dev`
- Container Registry `kleinanzeigenacrdev`
- PostgreSQL server `kleinanzeigen-db-dev`
- Redis cache `kleinanzeigen-redis-dev`

### 1.2 Enable ACR admin user
**Azure Portal → `kleinanzeigenacrdev` → Settings → Access keys → Admin user: toggle ON**

Required so the CI pipeline can push Docker images. Without this the build job fails.

### 1.3 Create a service principal for CI/CD
```bash
az ad sp create-for-rbac \
  --name "kleinanzeigen-ai-cicd" \
  --role Contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/kleinanzeigen-ai-dev-rg \
  --sdk-auth
```
Save the output — it contains `clientId`, `clientSecret`, `subscriptionId`, and `tenantId`.
These map to the `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, and `AZURE_SUBSCRIPTION_ID` GitHub secrets.

### 1.4 Grant the service principal AcrPush on the container registry
```bash
az role assignment create \
  --assignee <AZURE_CLIENT_ID> \
  --role AcrPush \
  --scope /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/kleinanzeigen-ai-dev-rg/providers/Microsoft.ContainerRegistry/registries/kleinanzeigenacrdev
```

### 1.5 Attach ACR to AKS (so pods can pull images)
```bash
az aks update \
  --name kleinanzeigen-aks-dev \
  --resource-group kleinanzeigen-ai-dev-rg \
  --attach-acr kleinanzeigenacrdev
```

### 1.6 Create the PostgreSQL database
After Terraform provisions the server, create the actual database:
```bash
az postgres flexible-server db create \
  --resource-group kleinanzeigen-ai-dev-rg \
  --server-name kleinanzeigen-db-dev \
  --database-name kleinanzeigen_ai
```

### 1.7 Allow AKS to reach PostgreSQL and Redis
By default both services block external traffic. Allow AKS node subnet:
```bash
# PostgreSQL firewall rule (replace with your AKS node IP range)
az postgres flexible-server firewall-rule create \
  --resource-group kleinanzeigen-ai-dev-rg \
  --name kleinanzeigen-db-dev \
  --rule-name allow-aks \
  --start-ip-address <AKS_NODE_IP_START> \
  --end-ip-address <AKS_NODE_IP_END>

# Redis (use private endpoint or allow AKS subnet in the portal)
# Azure Portal → kleinanzeigen-redis-dev → Settings → Firewall
```

### 1.8 Google OAuth — register redirect URI
**Google Cloud Console → APIs & Services → Credentials → your OAuth client**

Add the redirect URI:
```
https://<your-domain>/auth/google/callback
```

---

## 2. GitHub Actions Secrets
Go to: **GitHub → Repository → Settings → Secrets and variables → Actions → New repository secret**

| Secret name | What it is | Where to get it |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | See URL format below |
| `REDIS_URL` | Redis connection string | See URL format below |
| `SECRET_KEY` | Random string for JWT + session signing | Run: `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | Google Cloud Console → APIs & Services → Credentials |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | Google Cloud Console → APIs & Services → Credentials |
| `AZURE_CLIENT_ID` | Service principal client ID | Output of step 1.3 |
| `AZURE_CLIENT_SECRET` | Service principal secret | Output of step 1.3 |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID | Azure Portal → Subscriptions |
| `AKS_RESOURCE_GROUP` | Resource group containing AKS | `kleinanzeigen-ai-dev-rg` |
| `AKS_CLUSTER_NAME` | AKS cluster name | `kleinanzeigen-aks-dev` |
| `ACR_LOGIN_SERVER` | Container registry URL | `kleinanzeigenacrdev.azurecr.io` |
| `ACR_USERNAME` | Container registry username | Azure Portal → ACR → Access keys |
| `ACR_PASSWORD` | Container registry password | Azure Portal → ACR → Access keys |

---

## 3. Connection string formats

```
# PostgreSQL
postgresql://kleinanzeigenadmin:<password>@kleinanzeigen-db-dev.postgres.database.azure.com/kleinanzeigen_ai

# Redis (Azure Cache for Redis uses port 6380 with TLS — note rediss://)
rediss://:<access-key>@kleinanzeigen-redis-dev.redis.cache.windows.net:6380
```

---

## 4. Terraform sensitive variable (local runs only)
```bash
export TF_VAR_postgres_admin_password="your-strong-password"
```
Never commit this. For CI, add as GitHub Actions secret `TF_VAR_POSTGRES_ADMIN_PASSWORD_DEV`.

---

## 5. Final checklist — do in order
- [ ] Terraform applied successfully for dev environment (step 1.1)
- [ ] ACR admin user enabled (step 1.2)
- [ ] Service principal created and secrets saved (step 1.3)
- [ ] AcrPush role granted to service principal (step 1.4)
- [ ] ACR attached to AKS cluster (step 1.5)
- [ ] `kleinanzeigen_ai` database created in PostgreSQL (step 1.6)
- [ ] AKS firewall rules added for PostgreSQL and Redis (step 1.7)
- [ ] Google OAuth redirect URI registered (step 1.8)
- [ ] All 13 GitHub Actions secrets added (section 2)
- [ ] CI pipeline runs green end-to-end
