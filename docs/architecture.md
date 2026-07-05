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

## CI Pipeline

```
push to main / pull request
  │
  ├── lint          ruff check app/
  └── test          import check (api, worker, beat) + /healthz smoke test
```

See `.github/workflows/ci.yml`.

`app/shared/health_shim.py` opens a no-op socket alongside `worker` and
`beat` (see their Dockerfiles) so a container platform's startup probe has
something to check, even though neither is an HTTP service.

## Local Development

Docker Compose brings up PostgreSQL, Redis, the API, worker, and beat together. See `docker-compose.yml` and `.env.example`.

## Deployment

Self-managed: a VPS running the `docker-compose.prod.yml` stack behind
Caddy. See `docs/vps-deployment.md` for the full setup and day-2
operations (deploying updates, backups, restores).
