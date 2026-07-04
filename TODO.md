# TODO — Before first deploy

## Step 1 — Provision AWS resources

Run `infra/aws-setup.sh` (or provision manually via the AWS Console/CLI):

- **Amazon ECR** — to host Docker images
- **Amazon RDS for PostgreSQL** — production database
- **Amazon ElastiCache for Redis** — Celery broker
- **ECS cluster + services on Fargate**, an ALB, and the GitHub OIDC deploy role

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
| `AWS_DEPLOY_ROLE_ARN` | Output by `infra/aws-setup.sh` |

| Variable | Value |
|---|---|
| `AWS_REGION` | `eu-north-1` |
| `AWS_ACCOUNT_ID` | Your 12-digit AWS account ID |
| `PUBLIC_APP_URL` | ALB DNS name output by `infra/aws-setup.sh`, or your custom domain |

---

## Step 4 — Final checklist

- [ ] AWS resources provisioned (Step 1)
- [ ] Google OAuth redirect URI registered (Step 2)
- [ ] All GitHub Actions secrets and variables added (Step 3)
- [ ] Push to `main` — CI pipeline runs green end-to-end
