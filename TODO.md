# TODO — Before first deploy

---

## Step 1 — Run Terraform first
Terraform only needs ONE value from you upfront. Everything else it creates.

```bash
cd infrastructure/terraform/environments/dev
export TF_VAR_postgres_admin_password="choose-a-strong-password"
terraform init -backend-config=../../backend-config.dev.conf
terraform apply -var-file=terraform.tfvars
```

This creates: AKS cluster, Container Registry, PostgreSQL server + database, Redis cache.

---

## Step 2 — Get outputs from Terraform
After `terraform apply` completes, retrieve everything you need for GitHub secrets:

```bash
# Connection strings (sensitive — shown once, copy immediately)
terraform output -raw database_url
terraform output -raw redis_url
terraform output -raw acr_admin_password

# Non-sensitive
terraform output acr_login_server
terraform output acr_admin_username
terraform output aks_cluster_name
```

---

## Step 3 — Do these 4 things in Azure Portal / CLI

### 3.1 Enable ACR admin user
**Azure Portal → `kleinanzeigenacrdev` → Settings → Access keys → Admin user: toggle ON**

Without this the Docker push step in CI fails.

### 3.2 Create a service principal for CI/CD
```bash
az ad sp create-for-rbac \
  --name "kleinanzeigen-ai-cicd" \
  --role Contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/kleinanzeigen-ai-dev-rg
```
Save the output — it gives you `clientId`, `clientSecret`, `subscriptionId`.

### 3.3 Attach ACR to AKS (so pods can pull images)
```bash
az aks update \
  --name kleinanzeigen-aks-dev \
  --resource-group kleinanzeigen-ai-dev-rg \
  --attach-acr kleinanzeigenacrdev
```

### 3.4 Register Google OAuth redirect URI
**Google Cloud Console → APIs & Services → Credentials → your OAuth client → Authorised redirect URIs**
```
https://<your-domain>/auth/google/callback
```

---

## Step 4 — Add GitHub Actions secrets
**GitHub → Repository → Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Where to get the value |
|---|---|
| `DATABASE_URL` | `terraform output -raw database_url` |
| `REDIS_URL` | `terraform output -raw redis_url` |
| `SECRET_KEY` | Generate: `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID` | Google Cloud Console → APIs & Services → Credentials |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console → APIs & Services → Credentials |
| `AZURE_CLIENT_ID` | Output of step 3.2 (`clientId`) |
| `AZURE_CLIENT_SECRET` | Output of step 3.2 (`clientSecret`) |
| `AZURE_SUBSCRIPTION_ID` | Output of step 3.2 (`subscriptionId`) |
| `AKS_RESOURCE_GROUP` | `kleinanzeigen-ai-dev-rg` |
| `AKS_CLUSTER_NAME` | `terraform output aks_cluster_name` |
| `ACR_LOGIN_SERVER` | `terraform output acr_login_server` |
| `ACR_USERNAME` | `terraform output acr_admin_username` |
| `ACR_PASSWORD` | `terraform output -raw acr_admin_password` |

---

## Step 5 — Final checklist
- [ ] `terraform apply` completed successfully (step 1)
- [ ] Terraform outputs copied (step 2)
- [ ] ACR admin user enabled (step 3.1)
- [ ] Service principal created (step 3.2)
- [ ] ACR attached to AKS (step 3.3)
- [ ] Google OAuth redirect URI registered (step 3.4)
- [ ] All 13 GitHub Actions secrets added (step 4)
- [ ] Push to `main` — CI pipeline runs green end-to-end
