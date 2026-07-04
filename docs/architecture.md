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
  ├── build         docker build + push to Artifact Registry (api, worker, beat)
  ├── migrate       alembic upgrade head, run as a Cloud Run Job
  └── deploy        sync secrets to Secret Manager, deploy new Cloud Run
                     revisions (api, worker, beat)
```

Cloud Run only reaches Cloud SQL and Memorystore (both private-IP-only) via
a Serverless VPC Access connector, so every service/job attaches
`--vpc-connector=kleinanzeigen-connector`. `worker` and `beat` aren't HTTP
services, but Cloud Run still requires a listener on `$PORT` for its startup
probe — `app/shared/health_shim.py` opens a no-op socket for that, and
`--no-cpu-throttling --min-instances=1 --max-instances=1` keeps exactly one
instance of each always running (no request-driven scale-to-zero).

### GitHub Secrets required

| Secret | Description |
|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full WIF provider resource name (see `infra/gcp-setup.sh`) |
| `GCP_SERVICE_ACCOUNT` | Deploy service account email (see `infra/gcp-setup.sh`) |
| `DATABASE_URL` | PostgreSQL connection string (for the migrate job and Secret Manager) |

See `.github/workflows/build-and-push.yml` for the full list of app secrets synced to Secret Manager on deploy.

### GitHub Variables required

| Variable | Description |
|---|---|
| `GCP_PROJECT_ID` | GCP project ID the infrastructure runs in |
| `GCP_REGION` | GCP region, used to build Artifact Registry image URIs and for `--region` on every `gcloud run` call |

## Local Development

Docker Compose brings up PostgreSQL, Redis, the API, worker, and beat together. See `docker-compose.yml` and `.env.example`.

## Deployment

Deployed to Cloud Run. The CI pipeline builds and pushes images to Artifact Registry, runs migrations via a Cloud Run Job, then deploys new revisions of the `kleinanzeigen-api`, `kleinanzeigen-worker`, and `kleinanzeigen-beat` Cloud Run services with `gcloud run deploy`. See `infra/gcp-setup.sh` for one-time infrastructure provisioning (VPC, VPC connector, Cloud SQL, Memorystore, Artifact Registry, Secret Manager, service accounts, Workload Identity Federation for GitHub Actions).
