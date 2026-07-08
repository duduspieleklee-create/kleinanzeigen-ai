# Alembic Migration Guide

## Overview

Database schema changes are managed exclusively through Alembic migrations.
`Base.metadata.create_all()` is **not used** in the application — Alembic is the sole source of truth for the schema.

## Prerequisites

- `DATABASE_URL` environment variable must be set before running any Alembic command:
  ```bash
  export DATABASE_URL=postgresql://user:password@host:5432/kleinanzeigen_ai
  ```

## Common Commands

### Apply all pending migrations (bring DB up to date)
```bash
alembic upgrade heads
```

### Roll back the last migration
```bash
alembic downgrade -1
```

### Roll back to a specific revision
```bash
alembic downgrade 0001
```

### Check current revision applied to the DB
```bash
alembic current
```

### View full migration history
```bash
alembic history --verbose
```

### Auto-generate a new migration from model changes
```bash
alembic revision --autogenerate -m "describe your change here"
```
> Always review the generated file before applying it. Autogenerate is not perfect — it may miss some changes (e.g. server defaults, CHECK constraints).

## Naming Convention

Migration files follow the pattern: `{revision_id}_{short_description}.py`

Example: `0002_add_scrape_task_result_count.py`

Use sequential numeric IDs (`0001`, `0002`, …) for clarity.

## CI / Deployment

Run `alembic upgrade heads` as the first step before starting the API server. In the Helm chart, this is the correct place for an init container or a pre-start hook.

## Adding a New Model

1. Define the SQLAlchemy model in `app/shared/models.py`
2. Import it in `alembic/env.py` if it's in a new file (models already imported via `import app.shared.models`)
3. Run `alembic revision --autogenerate -m "add_<model_name>"`
4. Review and clean up the generated migration file
5. Run `alembic upgrade heads`
