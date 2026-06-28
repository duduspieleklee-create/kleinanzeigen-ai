# kleinanzeigen-ai

AI-powered tooling for Kleinanzeigen: REST API, async Celery worker, and Celery beat scheduler.

## Services

- **api** — FastAPI REST API
- **worker** — Celery async task worker  
- **beat** — Celery beat scheduler

## Infrastructure

- **Terraform** — cloud provisioning (dev / staging / prod)
- **Helm** — Kubernetes deployment charts

## Getting Started

See [docs/architecture.md](docs/architecture.md) for the system overview.
