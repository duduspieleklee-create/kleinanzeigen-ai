# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A multi-service Python application that scrapes classified ad listings from kleinanzeigen.de, stores structured results in PostgreSQL, and surfaces them through a FastAPI web UI. Users sign in with a username/password or Google OAuth, run recurring searches metered by a Stripe-billed plan (Basic/Core/Pro), and get web push (and optionally email) alerts when a search finds new listings. Three Docker services share a common `app/shared` package.

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
| `app/beat` | `app/beat/celery_beat.py` | Celery Beat scheduler (admin-search dispatch every 60 s, daily retention purge) |
| `app/shared` | — | SQLAlchemy models, DB session, URL builder, logging |

All three service Dockerfiles build from the repo root so they can `import app.shared.*`.

### Public site vs. app

`GET /` is a public marketing/pricing landing page (`landing.html`) for anonymous visitors; it redirects straight to `/dashboard` if the request already carries a valid session cookie. The actual login form lives at `GET /login`. `GET /billing/` (the plans/pricing page) is also viewable without a session — anonymous visitors see plans and prices with "sign up" CTAs instead of checkout forms.

### Request → scrape → result flow

1. User authenticates either with username/password (`POST /auth/login`) or Google OAuth (`GET /auth/google/login` → `GET /auth/google/callback`). Either path issues a JWT stored in an httponly cookie `access_token`. A username/password fallback for a single bootstrap admin account also exists on `/auth/login` (`settings.app_username`/`settings.app_password`), gated behind `settings.bootstrap_admin_enabled` — see "Bootstrap admin login" below.
2. `get_current_user` dependency (`app/api/dependencies.py`) checks the cookie first, then falls back to the `Authorization: Bearer` header, and verifies the user still exists and is active in the DB.
3. A scrape form POST to `POST /scrapes/` enforces plan limits (email verification, credits, active-search cap, interval floor — `app/api/routers/scrapes.py`), creates a `ScrapeTask` row (status `pending`), and calls `scrape_kleinanzeigen.delay(parameters, task_id)`.
4. The Celery worker (`app/worker/tasks.py`) picks up the task, sets status → `running`, fetches the URL, parses HTML with BeautifulSoup, saves up to 25 `ScrapeResult` rows (the first successful run per task is a free "baseline" — no credits charged, no notification sent), then sets status → `completed`.
5. If the task fails it retries up to 2 times with a 120 s countdown, then sets status → `failed`.
6. On a run that finds genuinely new listings (not the baseline), the worker sends a web push notification (`_send_push_notifications`) and, if the user has opted in, an email via Resend (`_send_email_notifications`) — both respect the user's quiet-hours/deals-only preferences from `/settings`.

### Beat-scheduled vs. API-triggered scrapes

`scrape_kleinanzeigen` handles both cases. When Beat fires it without a `task_id`, the function creates a new `ScrapeTask` owned by `settings.system_user_id`. When the API fires it with a `task_id`, it loads the existing task. This dual-path is in `_ensure_task()`.

### Self-re-scheduling

If `interval_seconds` is included in `parameters`, the task re-queues itself via `apply_async(countdown=interval_seconds)` at the end of a successful run. In non-dev environments the API enforces a minimum of 60 s (`MIN_INTERVAL_PROD`, the Pro plan's floor).

### Data model

```
User
 ├── ScrapeTask  (status: pending → running → completed | failed)
 │    └── ScrapeResult  (one row per listing)
 ├── PushSubscription  (one per browser/device)
 ├── Favorite  (→ ScrapeResult)
 └── TokenUsage  (FK to both User and ScrapeTask)

AdminSearch, Proxy, SystemSetting  — not user-owned; admin-managed globals
```

Models live in `app/shared/models.py`. Pydantic schemas for API I/O are in `app/api/models/schemas.py`.

### Account management & data retention (GDPR)

`app/api/routers/settings.py` exposes `GET /settings/export` (a JSON dump of everything the app stores about the caller) and `POST /settings/delete-account` (deletes the account and everything tied to it — requires typing the confirmation phrase `LÖSCHEN`, since password and Google-OAuth accounts have no common re-auth step). `app/worker/archival_task.py` purges `ScrapeResult` rows older than 14 days (favorited ones exempt) and `TokenUsage` rows older than 90 days; both are scheduled daily via `app/beat/celery_beat.py`'s `beat_schedule` — if you add a new archival task, it must be added there too, or it will sit registered with Celery but never actually run.

### Admin surface

`app/api/routers/admin.py` (all routes behind `require_admin`) manages `AdminSearch` (Beat-dispatched, admin-owned recurring searches, independent of any user's plan/credits) and the rotating `Proxy` pool (SSRF-guarded on add/retest via `app/shared/proxy.py::is_safe_proxy_url`). The UI for both lives in the `#tab-admin` pane of `dashboard.html`, visible only when `is_admin` is true.

### Bootstrap admin login

`POST /auth/login` has a fallback: if the submitted username/password match `settings.app_username`/`settings.app_password`, that account is created (or promoted) as admin. This exists to bootstrap the very first admin before any Google-OAuth admin exists via `ADMIN_EMAILS`. It's gated behind `settings.bootstrap_admin_enabled` (default `true`) and, outside `environment=dev`, `_reject_insecure_defaults_in_prod` (`app/api/config.py`) refuses to start unless `APP_PASSWORD` is both non-default and ≥12 characters. Set `BOOTSTRAP_ADMIN_ENABLED=false` once a real admin exists via Google OAuth.

## Key constraints and conventions

**Synchronous SQLAlchemy only.** The database layer uses `psycopg2` via a synchronous `create_engine`. Never use `asyncpg://` or `postgresql+asyncpg://` — the database module normalises those URLs away on startup. FastAPI route functions that touch the DB use `Depends(get_db)` and are not declared `async`.

**Alembic is the sole schema authority.** `Base.metadata.create_all()` is not called anywhere. All schema changes must go through a migration file. Migration IDs are sequential four-digit numbers (`0001`, `0002`, …). When adding a new model, define it in `app/shared/models.py` — `alembic/env.py` imports the whole module via `import app.shared.models`.

**Settings.** All configuration flows through `app/api/config.py` (`pydantic_settings.BaseSettings`). `DATABASE_URL` has no default and raises at startup if unset. `SYSTEM_USER_ID` (default `1`) must correspond to a real user row or Beat-scheduled tasks will fail FK constraints.

**Auth cookie vs. token.** `get_current_user` reads `request.cookies["access_token"]` first. The OAuth2 bearer scheme is present for API clients but the web UI always uses the cookie path.

**Ruff configuration.** Line length 100, target Python 3.11 (`pyproject.toml`). Run `ruff check app/` before committing — this is the only CI check that runs on PRs.

**CORS.** `allow_origins=["*"]` only when `settings.environment == "dev"`. Do not widen this for staging/prod.
