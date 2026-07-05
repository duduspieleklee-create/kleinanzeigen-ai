# kleinanzeigen-ai

Intelligent scraping and analytics platform for kleinanzeigen.de.j

## Overview

A multi-service Python application that scrapes, stores, and surfaces classified ad data from kleinanzeigen.de with Google OAuth authentication.

## Tech Stack

| Layer | Technologykl|
|---|---|
| API | FastAPI + Uvicorn |
| Task queue | Celery + Redis |
| Scheduler | Celery Beat |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Auth | Google OAuth 2.0 (Authlib) |
| CI | GitHub Actions (lint + test) |
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

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `SECRET_KEY` | ✅ | Session/JWT signing key — generate with `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID` | ✅ | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | ✅ | Google OAuth client secret |
| `ENVIRONMENT` | | `dev` / `staging` / `prod` (default: `dev`) |

## Database Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe change"
```

## CI

On every push to `main` and every pull request:
1. **lint** — ruff lints `app/`
2. **test** — import check for all three services + a `/healthz` smoke test

See `.github/workflows/ci.yml` and `docs/architecture.md` for details.

## Deployment

Self-managed VPS via Docker Compose + Caddy — see `docs/vps-deployment.md`.

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
