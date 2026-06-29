# Architecture

## Overview

`kleinanzeigen-ai` is a multi-service Python application for AI-powered Kleinanzeigen automation.

## Services

### API (`app/api`)
FastAPI-based REST API. Handles HTTP requests, authentication, and orchestration.

### Worker (`app/worker`)
Celery worker that processes async tasks (scraping, AI inference, notifications).

### Beat (`app/beat`)
Celery beat scheduler for periodic tasks (scheduled scrapes, report generation).

### Shared (`app/shared`)
Common utilities used across all services: URL builder, config, shared models.

## Infrastructure

### Terraform (`infrastructure/terraform`)
Cloud provisioning across three environments:
- `environments/dev` — development
- `environments/staging` — staging
- `environments/prod` — production

Reusable modules live in `modules/`.

## CI/CD

`.github/workflows/build-and-push.yml` builds Docker images for all three services and runs database migrations on every push to `main`.
