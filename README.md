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
| Container registry | Artifact Registry |
| CI/CD | GitHub Actions → Cloud Run |
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

## CI/CD

On every push to `main`:
1. **lint** — ruff lints `app/`
2. **build** — builds and pushes Docker images to Artifact Registry
3. **migrate** — runs `alembic upgrade head` via a Cloud Run Job
4. **deploy** — syncs secrets to Secret Manager and deploys new Cloud Run revisions

See `.github/workflows/build-and-push.yml` and `docs/architecture.md` for details.

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
- `prod` — Google Cloud (Cloud Run, Cloud SQL for PostgreSQL, Memorystore for Redis) via GitHub Actions
- self-managed VPS — Docker Compose on your own Ubuntu server, see `docs/vps-deployment.md`
