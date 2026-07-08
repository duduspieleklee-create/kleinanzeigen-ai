# kleinanzeigen-ai v1

Intelligent scraping and analytics platform for kleinanzeigen.de.

## Overview

A multi-service Python application that scrapes, stores, and surfaces classified ad data from kleinanzeigen.de. Users sign up with a username/password or Google OAuth, set up recurring searches metered by a Stripe-billed plan (Basic/Core/Pro), and get web push and (optionally) email alerts when a search finds new listings, with deal-price and seller-trust scoring on Core/Pro.

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Task queue | Celery + Redis |
| Scheduler | Celery Beat |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Auth | Username/password + Google OAuth 2.0 (Authlib) |
| Billing | Stripe Checkout, Billing Portal, and webhooks |
| Notifications | Web Push (pywebpush) + email (Resend) |
| CI/CD | GitHub Actions (lint + test + SSH deploy) |
| Local dev | Docker Compose |

## Services

| Service | Dockerfile | Purpose |
|---|---|---|
| `api` | `app/api/Dockerfile` | FastAPI REST API + web UI |
| `worker` | `app/worker/Dockerfile` | Celery worker (scraping tasks) |
| `beat` | `app/beat/Dockerfile` | Celery Beat scheduler |

## Local Development

```bash
cp .env.example .env
# Edit .env with your values

docker compose up --build
```

App available at `http://localhost:8000`.

## Environment Variables

Full list with comments in `.env.example`. The essentials:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `SECRET_KEY` | ✅ | Session/JWT signing key — generate with `openssl rand -hex 32` |
| `ENVIRONMENT` | | `dev` / `staging` / `prod` (default: `dev`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | | Google OAuth login — leave empty to disable the Google button |
| `BOOTSTRAP_ADMIN_ENABLED` / `APP_USERNAME` / `APP_PASSWORD` | | Fallback admin login for creating the first admin account; ≥12-char password required outside dev |
| `ADMIN_EMAILS` | | Comma-separated Google emails auto-promoted to admin on login |
| `RESEND_API_KEY` / `EMAIL_FROM` | | Verification and new-results emails; leave empty to disable email sending |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` / `VAPID_EMAIL` | | Web push notifications; leave empty to disable |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_CORE` / `STRIPE_PRICE_PRO` | | Paid plans via Stripe; leave empty to keep everyone on the free Basic plan |
| `PUBLIC_BASE_URL` | | Public origin for OAuth/Stripe redirect URLs and email links |

## Database Migrations

```bash
# Apply all migrations
alembic upgrade heads

# Create a new migration after model changes
alembic revision --autogenerate -m "describe change"
```

## CI/CD

On every push to `main` and every pull request:
1. **lint** — ruff lints `app/`
2. **test** — import check for all three services + a `/healthz` smoke test

On a push to `main` only, once lint + test pass:

3. **deploy** — SSHes into the VPS and runs `git pull` + `alembic upgrade heads` + `docker compose up -d --build`

See `.github/workflows/ci-cd.yml` and `docs/architecture.md` for details.

## Deployment

Self-managed VPS via Docker Compose + Caddy, auto-deployed on every merge to `main` — see `docs/vps-deployment.md`.

## Repository Structure

```
app/
  api/       FastAPI application, auth, routers, templates
  worker/    Celery worker tasks
  beat/      Celery Beat scheduler
  shared/    Shared models, database, utilities
alembic/     Database migration scripts
docs/        Architecture and runbook documentation
docker-compose.yml
docker-compose.prod.yml
deploy/      Caddyfile for self-managed VPS deployments
requirements.txt
```

## Environments

- `dev` — local Docker Compose
- `prod` — self-managed VPS (Docker Compose + Caddy), see `docs/vps-deployment.md`
