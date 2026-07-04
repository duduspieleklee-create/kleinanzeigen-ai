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
  ├── build         docker build + push to Amazon ECR (api, worker, beat)
  ├── migrate       alembic upgrade head
  └── deploy        sync secrets to AWS Secrets Manager, roll out new ECS task
                     definitions (api, worker, beat) on Fargate
```

### GitHub Secrets required

| Secret | Description |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | IAM role ARN assumed via GitHub OIDC (see `infra/aws-setup.sh`) |
| `DATABASE_URL` | PostgreSQL connection string (for migration step and Secrets Manager) |

See `.github/workflows/build-and-push.yml` for the full list of app secrets synced to Secrets Manager on deploy.

### GitHub Variables required

| Variable | Description |
|---|---|
| `AWS_REGION` | AWS region the infrastructure runs in |
| `AWS_ACCOUNT_ID` | AWS account ID, used to build ECR image URIs |
| `PUBLIC_APP_URL` | ALB DNS name or custom domain, used by the post-deploy smoke test |

## Local Development

Docker Compose brings up PostgreSQL, Redis, the API, worker, and beat together. See `docker-compose.yml` and `.env.example`.

## Deployment

Deployed to Amazon ECS on Fargate. The CI pipeline builds and pushes images to ECR, runs migrations, then registers new ECS task definitions and rolls them out with `aws-actions/amazon-ecs-deploy-task-definition`. See `infra/aws-setup.sh` for one-time infrastructure provisioning (ECR, RDS, ElastiCache, ECS cluster/services, ALB, IAM roles) and `infra/ecs/task-def-*.json` for the task definition templates.
