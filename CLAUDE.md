# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A multi-service Python application that scrapes classified ad listings from kleinanzeigen.de, stores structured results in PostgreSQL, and surfaces them through a FastAPI web UI with Google OAuth authentication. Three Docker services share a common `app/shared` package.

## Commands

```bash
# Local development (starts api, worker, beat, postgres, redis)
cp .env.example .env   # then fill in SECRET_KEY at minimum
docker compose up --build

# Lint (mirrors CI)
ruff check app/

# Database migrations
alembic upgrade head                                 # apply pending
alembic revision --autogenerate -m "describe change" # generate from model changes
alembic downgrade -1                                 # roll back one
alembic current                                      # check applied revision
```

`DATABASE_URL` must be set before any `alembic` command.

There are no automated tests yet.

## Architecture

### Service boundaries

| Service | Entry point | Role |
|---|---|---|
| `app/api` | `app/api/main.py` | FastAPI REST API + Jinja2 web UI |
| `app/worker` | `app/worker/celery_app.py` | Celery worker executing scrape tasks |
| `app/beat` | `app/beat/celery_beat.py` | Celery Beat scheduler (30-min periodic scrape) |
| `app/shared` | — | SQLAlchemy models, DB session, URL builder, logging |

All three service Dockerfiles build from the repo root so they can `import app.shared.*`.

### Request → scrape → result flow

1. User authenticates via Google OAuth (`/auth/login/google`). On success, a JWT is minted and stored in an httponly cookie `access_token`.
2. `get_current_user` dependency (`app/api/dependencies.py`) checks the cookie first, then falls back to the `Authorization: Bearer` header.
3. A scrape form POST to `POST /scrapes/` creates a `ScrapeTask` row (status `pending`) and calls `scrape_kleinanzeigen.delay(parameters, task_id)`.
4. The Celery worker (`app/worker/tasks.py`) picks up the task, sets status → `running`, fetches the URL, parses HTML with BeautifulSoup, saves up to 25 `ScrapeResult` rows, then sets status → `completed`.
5. If the task fails it retries up to 2 times with a 120 s countdown, then sets status → `failed`.

### Beat-scheduled vs. API-triggered scrapes

`scrape_kleinanzeigen` handles both cases. When Beat fires it without a `task_id`, the function creates a new `ScrapeTask` owned by `settings.system_user_id`. When the API fires it with a `task_id`, it loads the existing task. This dual-path is in `_ensure_task()`.

### Self-re-scheduling

If `interval_seconds` is included in `parameters`, the task re-queues itself via `apply_async(countdown=interval_seconds)` at the end of a successful run. In non-dev environments the API enforces a minimum of 60 s (`MIN_INTERVAL_PROD`, the Pro plan's floor).

### Data model

```
User
 └── ScrapeTask  (status: pending → running → completed | failed)
      └── ScrapeResult  (one row per listing)
```

Models live in `app/shared/models.py`. Pydantic schemas for API I/O are in `app/api/models/schemas.py`.

## Key constraints and conventions

**Synchronous SQLAlchemy only.** The database layer uses `psycopg2` via a synchronous `create_engine`. Never use `asyncpg://` or `postgresql+asyncpg://` — the database module normalises those URLs away on startup. FastAPI route functions that touch the DB use `Depends(get_db)` and are not declared `async`.

**Alembic is the sole schema authority.** `Base.metadata.create_all()` is not called anywhere. All schema changes must go through a migration file. Migration IDs are sequential four-digit numbers (`0001`, `0002`, …). When adding a new model, define it in `app/shared/models.py` — `alembic/env.py` imports the whole module via `import app.shared.models`.

**Settings.** All configuration flows through `app/api/config.py` (`pydantic_settings.BaseSettings`). `DATABASE_URL` has no default and raises at startup if unset. `SYSTEM_USER_ID` (default `1`) must correspond to a real user row or Beat-scheduled tasks will fail FK constraints.

**Auth cookie vs. token.** `get_current_user` reads `request.cookies["access_token"]` first. The OAuth2 bearer scheme is present for API clients but the web UI always uses the cookie path.

**Ruff configuration.** Line length 100, target Python 3.11 (`pyproject.toml`). Run `ruff check app/` before committing — this is the only CI check that runs on PRs.

**CORS.** `allow_origins=["*"]` only when `settings.environment == "dev"`. Do not widen this for staging/prod.
