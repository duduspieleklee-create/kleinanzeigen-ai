## Current Status (Milestone 1)

- [x] Project structure
- [x] FastAPI + Celery setup
- [x] Basic authentication
- [x] URL Builder
- [x] Docker Compose
- [ ] Celery task fully working + saving results
- [ ] Terraform ready for AKS
- [ ] Deployment via Octopus Deploy


# kleinanzeigen-ai

Intelligent scraping and analytics platform for kleinanzeigen.de.

## Overview

This project provides a scalable web scraping solution with an intelligence layer for classifieds data from kleinanzeigen.de.

## Tech Stack

- **Backend**: FastAPI + Celery
- **Database**: Azure Database for PostgreSQL
- **Queue**: Azure Cache for Redis
- **Infrastructure**: Terraform + Azure AKS
- **Deployment**: GitHub Actions + Octopus Deploy + Helm
- **Orchestration**: Kubernetes (AKS)

## Repository Structure

- `app/` – Application code (API, Worker, Beat)
- `infrastructure/` – Terraform and Helm charts
- `.github/workflows/` – CI/CD pipelines

## Getting Started

See [docs/architecture.md](docs/architecture.md) for system overview.

## Environments

- `dev`
- `staging`
- `prod`
