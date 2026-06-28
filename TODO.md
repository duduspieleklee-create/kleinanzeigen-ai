# TODO — Variables to deliver before first deploy

## GitHub Actions Secrets
Go to: **GitHub → Repository → Settings → Secrets and variables → Actions → New repository secret**

| Secret name | What it is | Where to get it |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Azure Portal → `kleinanzeigen-ai-dev-rg` → `kleinanzeigen-db-dev` → Connection strings |
| `REDIS_URL` | Redis connection string | Azure Portal → `kleinanzeigen-ai-dev-rg` → `kleinanzeigen-redis-dev` → Access keys |
| `SECRET_KEY` | Random string for JWT signing | Generate: `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | Google Cloud Console → APIs & Services → Credentials |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | Google Cloud Console → APIs & Services → Credentials |
| `AZURE_CLIENT_ID` | Service principal client ID | Azure Portal → Azure Active Directory → App registrations |
| `AZURE_CLIENT_SECRET` | Service principal secret | Azure Portal → Azure Active Directory → App registrations → Certificates & secrets |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID | Azure Portal → Subscriptions |
| `AKS_RESOURCE_GROUP` | Resource group containing AKS | `kleinanzeigen-ai-dev-rg` (dev) / `kleinanzeigen-ai-prod-rg` (prod) |
| `AKS_CLUSTER_NAME` | AKS cluster name | `kleinanzeigen-aks-dev` (dev) / `kleinanzeigen-aks-prod` (prod) |
| `ACR_LOGIN_SERVER` | Container registry URL | Azure Portal → `kleinanzeigenacrdev` → Access keys → Login server |
| `ACR_USERNAME` | Container registry username | Azure Portal → `kleinanzeigenacrdev` → Access keys → Username |
| `ACR_PASSWORD` | Container registry password | Azure Portal → `kleinanzeigenacrdev` → Access keys → Password |

## Terraform (local / CI only — never commit)
Set as environment variables before running `terraform apply`:

```bash
export TF_VAR_postgres_admin_password="your-strong-password"
```

For CI, add as a GitHub Actions secret named `TF_VAR_POSTGRES_ADMIN_PASSWORD_DEV` and `TF_VAR_POSTGRES_ADMIN_PASSWORD_PROD`.

## URL formats

```
# PostgreSQL (replace placeholders)
postgresql://kleinanzeigenadmin:<password>@kleinanzeigen-db-dev.postgres.database.azure.com/kleinanzeigen_ai

# Redis (Azure Cache for Redis uses port 6380 with TLS)
rediss://:<access-key>@kleinanzeigen-redis-dev.redis.cache.windows.net:6380
```

## Azure Tenant ID (already in repo)
`f196df42-b27f-416b-b16f-d6f83a94cd0f` — already committed to `secret-provider-class.yaml` and the CI workflow.

## Checklist
- [ ] All 13 GitHub Actions secrets added
- [ ] `TF_VAR_postgres_admin_password` set locally before running Terraform
- [ ] Google OAuth redirect URI set in Google Cloud Console:
      `https://<your-domain>/auth/google/callback`
- [ ] AKS cluster running and `kubectl` context verified
- [ ] ACR admin access enabled (Azure Portal → ACR → Access keys → Admin user: Enabled)
