# TODO — Before first deploy

## Step 1 — Provision Azure resources

Provision the following manually in the Azure Portal or via Azure CLI:

- **Azure Container Registry** — to host Docker images
- **Azure Database for PostgreSQL Flexible Server** — production database
- **Azure Cache for Redis** — Celery broker

Note connection strings — you'll need them in Step 3.

---

## Step 2 — Register Google OAuth

In **Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 client**, add the redirect URI:

```
https://<your-domain>/auth/google/callback
```

---

## Step 3 — Add GitHub Actions secrets

**GitHub → Repository → Settings → Secrets and variables → Actions**

| Secret | Value |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID` | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console |
| `ACR_LOGIN_SERVER` | e.g. `myregistry.azurecr.io` |
| `ACR_USERNAME` | ACR admin username |
| `ACR_PASSWORD` | ACR admin password |
| `OCTOPUS_SERVER_URL` | e.g. `https://yourinstance.octopus.app` |
| `OCTOPUS_API_KEY` | Octopus → Profile → API Keys |

---

## Step 4 — Set up Octopus Deploy

1. Create a project named **`kleinanzeigen-ai`** in Octopus Deploy
2. Create environments: **Dev**, **Staging**, **Prod**
3. Configure a deployment process that pulls images from ACR and runs three containers: `api`, `worker`, `beat`
4. Set project variables: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` per environment

---

## Step 5 — Final checklist

- [ ] Azure resources provisioned (Step 1)
- [ ] Google OAuth redirect URI registered (Step 2)
- [ ] All 10 GitHub Actions secrets added (Step 3)
- [ ] Octopus project and environments configured (Step 4)
- [ ] Push to `main` — CI pipeline runs green end-to-end
