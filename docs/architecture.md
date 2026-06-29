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
push to main
  │
  ├── lint          ruff check app/
  ├── build         docker build + push to ACR (api, worker, beat)
  ├── migrate       alembic upgrade head
  └── deploy        Octopus Deploy → Dev environment
```

### GitHub Secrets required

| Secret | Description |
|---|---|
| `ACR_LOGIN_SERVER` | Azure Container Registry hostname |
| `ACR_USERNAME` | ACR username |
| `ACR_PASSWORD` | ACR password |
| `DATABASE_URL` | PostgreSQL connection string (for migration step) |
| `OCTOPUS_SERVER_URL` | Octopus Deploy server URL |
| `OCTOPUS_API_KEY` | Octopus Deploy API key |

## Local Development

Docker Compose brings up PostgreSQL, Redis, the API, worker, and beat together. See `docker-compose.yml` and `.env.example`.

## Deployment

Releases are managed by Octopus Deploy. The CI pipeline creates a release and deploys it to the `Dev` environment automatically. Promotion to `Staging` and `Prod` is done manually inside Octopus.
