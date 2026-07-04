# TODO — Before first deploy

## Step 1 — Provision Google Cloud resources

Run `infra/gcp-setup.sh` (or provision manually via the Google Cloud Console/CLI):

- **Artifact Registry** — to host Docker images
- **Cloud SQL for PostgreSQL** — production database (private IP only)
- **Memorystore for Redis** — Celery broker (private IP only)
- **Serverless VPC Access connector** — lets Cloud Run reach both of the above
- **Secret Manager** secrets, a Cloud Run runtime service account, and a
  Workload Identity Federation identity for GitHub Actions

Note connection strings — you'll need them in Step 3.

---

## Step 2 — Register Google OAuth

In **Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 client**, add the redirect URI:

```
https://<your-domain>/auth/google/callback
```

---

## Step 3 — Add GitHub Actions secrets and variables

**GitHub → Repository → Settings → Secrets and variables → Actions**

| Secret | Value |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID` | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Output by `infra/gcp-setup.sh` |
| `GCP_SERVICE_ACCOUNT` | Output by `infra/gcp-setup.sh` |

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | Output by `infra/gcp-setup.sh` |
| `GCP_REGION` | `europe-north1` |

---

## Step 4 — Final checklist

- [ ] Google Cloud resources provisioned (Step 1)
- [ ] Google OAuth redirect URI registered (Step 2)
- [ ] All GitHub Actions secrets and variables added (Step 3)
- [ ] Push to `main` — CI pipeline runs green end-to-end
