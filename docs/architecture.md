# Architecture

## Overview

`kleinanzeigen-ai` is a multi-service Python application for AI-powered Kleinanzeigen automation. It scrapes classified ad listings, stores structured results in PostgreSQL, and surfaces them through a FastAPI web interface with Google OAuth authentication.

## Services

### API (`app/api`)
FastAPI-based REST API and web UI. Handles HTTP requests, Google OAuth authentication, session management, and orchestration of scrape jobs.

- Entry point: `app/api/main.py`
- Auth: `app/api/routers/auth.py` (Google OAuth via Authlib)
- Scrapes: `app/api/routers/scrapes.py` (POST to create job, GET to poll status)

### Worker (`app/worker`)
Celery worker that executes scraping tasks asynchronously. Fetches listings from kleinanzeigen.de, parses HTML with BeautifulSoup, and saves `ScrapeResult` rows linked to the originating `ScrapeTask`.

### Beat (`app/beat`)
Celery Beat scheduler. Dispatches periodic scrape jobs (currently every 30 minutes for a hardcoded search). Schedule is defined in `app/beat/celery_beat.py`.

### Shared (`app/shared`)
Common utilities used across all services: database session, SQLAlchemy models, URL builder, and logging config.

## Data Model

```
User
 └── ScrapeTask (status: pending → running → completed/failed)
      └── ScrapeResult (one row per listing)
```

## CI/CD Pipeline

```
push to main / pull request
  │
  ├── lint          ruff check app/
  ├── test          import check (api, worker, beat) + /healthz smoke test
  └── deploy        (main branch only, after lint+test pass)
                     SSH into the VPS: git pull, alembic upgrade heads,
                     docker compose up -d --build
```

See `.github/workflows/ci-cd.yml`. `deploy` uses `appleboy/ssh-action` and
runs only on a direct push to `main` (never on pull requests).

`app/shared/health_shim.py` opens a no-op socket alongside `worker` and
`beat` (see their Dockerfiles) so a container platform's startup probe has
something to check, even though neither is an HTTP service.

### GitHub Secrets required

| Secret | Description |
|---|---|
| `VPS_HOST` | VPS hostname or IP the `deploy` job SSHes into |
| `VPS_USER` | SSH user (must have `docker` group membership and own `/opt/kleinanzeigen-ai`) |
| `VPS_SSH_PASSWORD` | That user's SSH login password |

`VPS_PORT` is an optional secret (defaults to `22`) if the VPS uses a non-standard SSH port.

Optional secrets the `deploy` job injects into the server's `.env` when set: `RESEND_API_KEY`, `EMAIL_FROM`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` (Cloudflare Turnstile bot protection on the login/register forms — see [turnstile.md](turnstile.md)).

## Local Development

Docker Compose brings up PostgreSQL, Redis, the API, worker, and beat together. See `docker-compose.yml` and `.env.example`.

## Deployment

Self-managed: a VPS running the `docker-compose.prod.yml` stack behind
Caddy, auto-deployed by the `deploy` CI job on every merge to `main`. See
`docs/vps-deployment.md` for the full setup, manual deploy steps, and
day-2 operations (backups, restores).
