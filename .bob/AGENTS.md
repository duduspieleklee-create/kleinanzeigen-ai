# Kleinanzeigen AI Project Context

## Project Overview

An intelligent scraping and analytics platform for kleinanzeigen.de (German classifieds). Users create recurring searches with AI-powered deal scoring, seller trust analysis, and smart notifications via web push and email.

**Business Model:** Freemium SaaS with Stripe billing (Basic/Core/Pro plans)

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API** | FastAPI + Uvicorn | REST API + web UI |
| **Task Queue** | Celery + Redis | Async scraping tasks |
| **Scheduler** | Celery Beat | Recurring search execution |
| **Database** | PostgreSQL + SQLAlchemy | Data persistence |
| **Migrations** | Alembic | Schema versioning |
| **Auth** | Username/password + Google OAuth 2.0 | User authentication |
| **Billing** | Stripe Checkout + webhooks | Subscription management |
| **Notifications** | pywebpush + Resend | Web push + email alerts |
| **Monitoring** | Sentry | Error tracking |
| **Deployment** | Docker Compose + Caddy | Self-managed VPS |
| **CI/CD** | GitHub Actions | Lint, test, deploy on merge to main |

## Architecture

### Service Structure

```
app/
├── api/          # FastAPI application (port 8000)
│   ├── main.py           # App entry point
│   ├── routers/          # API endpoints
│   │   ├── auth.py       # Login, register, OAuth
│   │   ├── scrapes.py    # Search CRUD
│   │   ├── billing.py    # Stripe integration
│   │   ├── admin.py      # Admin panel
│   │   ├── settings.py   # User preferences
│   │   ├── push.py       # Web push subscriptions
│   │   └── locations.py  # Location autocomplete
│   ├── templates/        # Jinja2 HTML templates
│   ├── static/           # CSS, JS, PWA manifest
│   ├── security.py       # Password hashing, JWT
│   ├── emailer.py        # Email sending (Resend)
│   └── turnstile.py      # Cloudflare Turnstile verification
│
├── worker/       # Celery worker (scraping tasks)
│   ├── celery_app.py     # Celery configuration
│   ├── tasks.py          # Main scraping task
│   ├── seller_scraper.py # Seller trust scoring
│   ├── archival_task.py  # Old result cleanup
│   └── category_rotation_task.py  # Admin search rotation
│
├── beat/         # Celery Beat scheduler
│   └── celery_beat.py    # Schedule configuration
│
└── shared/       # Shared utilities
    ├── models.py         # SQLAlchemy models
    ├── database.py       # DB session management
    ├── plans.py          # Plan limits & credit system
    ├── pricing.py        # Stripe price IDs
    ├── proxy.py          # Rotating proxy logic
    ├── smart_alerts.py   # AI-powered summaries
    ├── token_tracking.py # LLM token usage tracking
    ├── url_builder.py    # kleinanzeigen.de URL construction
    ├── email_notifications.py  # Email alert logic
    ├── category_rotation.py    # Category-based search rotation
    ├── metrics.py        # Prometheus metrics
    ├── sentry.py         # Sentry initialization
    └── logging_config.py # Structured logging
```

## Database Models

### Core Models

**User**
- Authentication: username/email + hashed_password OR Google OAuth
- Plan: basic (free) / core / pro
- Credits: weekly result credits (refilled lazily)
- Billing: stripe_customer_id, stripe_subscription_id
- Preferences: push/email notifications, quiet hours, deals_only
- Flags: is_admin, email_verified, has_completed_tutorial, trial_used

**ScrapeTask**
- User's recurring search configuration
- Fields: url, parameters (JSON), status, interval
- baseline_done: false until first run (baseline is free, no credits charged)
- error_message: user-facing error explanation
- last_summary: AI-generated summary of last notifying run

**ScrapeResult**
- Individual listing found by a task
- Fields: title, price, price_value, location, url, image_url, description
- Seller info: seller_id, seller_name, seller_rating, seller_badges, seller_active_since, seller_listings_count
- trust_score: calculated seller trustworthiness (0-100)
- Unique constraint: (task_id, url) - prevents duplicate results per task

**PushSubscription**
- Web push endpoint for a user's device
- Fields: endpoint, p256dh, auth (VAPID keys)

**AdminSearch**
- Admin-managed recurring searches (not tied to a user)
- is_rotation_managed: true for category rotation task's searches
- Runs on schedule (interval_minutes, next_run_at)

**Proxy**
- Rotating proxy pool for scraping
- is_active: only tested/working proxies are used
- last_status, last_tested_at: health check results

**TokenUsage**
- Tracks LLM token consumption per user/task/day
- Used for cost monitoring and potential future billing

**Favorite**
- User's saved/bookmarked listings

**SystemSetting**
- Key/value store for global feature flags (e.g., "rotating_proxy_enabled")

## Key Features

### 1. Subscription Plans (app/shared/plans.py)

| Plan | Price | Searches | Credits/Week | Features |
|------|-------|----------|--------------|----------|
| Basic | Free | 3 | 10 | Basic alerts |
| Core | €4.99/mo | 10 | 100 | Deal scoring, 3-day trial |
| Pro | €9.99/mo | Unlimited | 500 | All features, seller trust |

**Credit System:**
- 1 credit = 1 new listing found (after baseline)
- Refilled weekly (credits_reset_at)
- Enforced in worker/tasks.py before saving results

### 2. Smart Alerts (app/shared/smart_alerts.py)

AI-powered notification summaries using LLM:
- Analyzes new listings vs. previous results
- Generates concise, actionable summaries
- Highlights great deals and trusted sellers
- Stored in ScrapeTask.last_summary

### 3. Seller Trust Scoring (app/worker/seller_scraper.py)

Calculates trust_score (0-100) based on:
- Account age (seller_active_since)
- Number of active listings (seller_listings_count)
- Seller rating (seller_rating)
- Badges (seller_badges)
- Pro plan exclusive feature

### 4. Proxy Rotation (app/shared/proxy.py)

- Admin-managed proxy pool (Proxy model)
- Health checks via /admin/proxies/test
- Automatic rotation on scraping failures
- Enabled via SystemSetting: rotating_proxy_enabled

### 5. Category Rotation (app/worker/category_rotation_task.py)

Admin feature to automatically rotate searches through categories:
- Creates/updates AdminSearch rows with is_rotation_managed=true
- Cycles through predefined categories
- Helps maintain fresh baseline data

## Code Conventions

### General
- **Async/await:** Use consistently throughout FastAPI and Celery tasks
- **Type hints:** Required for all function signatures
- **Logging:** Use structured logging (app/shared/logging_config.py)
- **Error handling:** Catch specific exceptions, log to Sentry, return user-friendly messages

### Database
- **Migrations:** Always use Alembic for schema changes
- **Queries:** Use SQLAlchemy ORM, avoid raw SQL
- **Transactions:** Use `db.commit()` explicitly, handle rollbacks
- **Indexes:** Add for foreign keys and frequently queried columns

### API
- **Routers:** Group related endpoints in separate router files
- **Dependencies:** Use FastAPI dependency injection (app/api/dependencies.py)
- **Validation:** Use Pydantic models (app/api/models/schemas.py)
- **Auth:** Require `current_user` dependency for protected routes

### Worker Tasks
- **Idempotency:** Tasks should be safe to retry
- **Error handling:** Catch exceptions, update task status, log to Sentry
- **Credits:** Check and deduct credits before saving results
- **Notifications:** Send push/email only for non-baseline runs with new results

### Testing
- **Location:** tests/ directory
- **Framework:** pytest (when implemented)
- **Coverage:** Focus on critical paths (billing, credits, scraping)

## Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `SECRET_KEY` - Session/JWT signing (generate with `openssl rand -hex 32`)

**Optional but recommended:**
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - Google OAuth
- `RESEND_API_KEY` / `EMAIL_FROM` - Email notifications
- `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` / `VAPID_EMAIL` - Web push
- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` - Billing
- `SENTRY_DSN` - Error tracking
- `PUBLIC_BASE_URL` - For OAuth/Stripe redirects

## Common Tasks

### Run locally
```bash
docker compose up --build
```

### Create migration
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Deploy to production
```bash
git push origin main  # CI/CD auto-deploys
```

### Test proxy
```bash
curl -X POST http://localhost:8000/admin/proxies/test
```

### Check logs
```bash
docker compose logs -f api
docker compose logs -f worker
```

## Recent Work Areas

Based on the codebase structure, recent development has focused on:

1. **Billing & Plans** (alembic/versions/0011_add_plans_and_billing.py)
   - Stripe integration
   - Credit system
   - Plan enforcement

2. **Email Verification** (alembic/versions/0012_add_email_verification.py)
   - Verification tokens
   - Email sending via Resend

3. **Smart Alerts** (app/shared/smart_alerts.py)
   - LLM-powered summaries
   - Token tracking

4. **Seller Trust Scoring** (alembic/versions/0016_add_account_age_and_listings_to_trust_score.py)
   - Seller data scraping
   - Trust score calculation

5. **Category Rotation** (alembic/versions/0024_admin_search_parity_and_rotation.py)
   - Admin search management
   - Automatic category cycling

6. **Notification Preferences** (alembic/versions/0018_add_user_notification_preferences.py)
   - Push/email toggles
   - Quiet hours
   - Deals-only mode

## Known Patterns

### Adding a new feature
1. Update models.py
2. Create Alembic migration
3. Add API endpoint in routers/
4. Update templates if needed
5. Add worker task if async processing required
6. Update plans.py if feature is plan-gated
7. Add logging and Sentry tracking

### Debugging scraping issues
1. Check worker logs: `docker compose logs -f worker`
2. Verify proxy status: GET /admin/proxies
3. Check ScrapeTask.error_message in database
4. Review Sentry for full tracebacks
5. Test URL manually with curl/browser

### Handling billing webhooks
1. Stripe sends webhook to /billing/webhook
2. Verify signature with STRIPE_WEBHOOK_SECRET
3. Update User model (plan, stripe_customer_id, etc.)
4. Enforce plan limits via plans.enforce_plan_limits()
5. Log event to Sentry for audit trail

## Security Considerations

- **Passwords:** Hashed with bcrypt (app/api/security.py)
- **JWT tokens:** Signed with SECRET_KEY, 30-day expiry
- **OAuth:** Google OAuth 2.0 via Authlib
- **Stripe webhooks:** Signature verification required
- **Turnstile:** Cloudflare bot protection on registration
- **Rate limiting:** Not yet implemented (TODO)
- **SQL injection:** Protected by SQLAlchemy ORM
- **XSS:** Jinja2 auto-escaping enabled

## Monitoring & Observability

- **Sentry:** Error tracking and performance monitoring
- **Prometheus:** Metrics exposed at /metrics (app/shared/metrics.py)
- **Structured logging:** JSON logs with context (app/shared/logging_config.py)
- **Health checks:** /healthz endpoint for all services

## Deployment

- **Platform:** Self-managed VPS (Docker Compose + Caddy)
- **CI/CD:** GitHub Actions (.github/workflows/ci-cd.yml)
- **Process:** Lint → Test → Deploy (on merge to main)
- **Rollback:** `git revert` + push to main
- **Backups:** Manual via deploy/backup.sh

## Documentation

- `docs/architecture.md` - System design and data flow
- `docs/vps-deployment.md` - Production deployment guide
- `docs/alembic.md` - Migration workflow
- `docs/url_builder.md` - kleinanzeigen.de URL construction
- `docs/translation-workflow.md` - i18n process (if implemented)

## Development Preferences

- **Editor:** VS Code recommended (Python, Docker extensions)
- **Python version:** 3.11+
- **Code style:** Follow existing patterns, use ruff for linting
- **Commit messages:** Conventional commits preferred
- **Branch strategy:** Feature branches → PR → main
- **Review process:** Self-review before merge (solo dev project)

## Troubleshooting

### Worker not processing tasks
- Check Redis connection: `docker compose logs redis`
- Verify Celery worker is running: `docker compose ps worker`
- Check for task errors: `docker compose logs worker`

### Scraping failures
- Verify proxy health: GET /admin/proxies
- Check kleinanzeigen.de availability
- Review ScrapeTask.error_message
- Check Sentry for detailed tracebacks

### Email not sending
- Verify RESEND_API_KEY is set
- Check email_notifications_enabled in User model
- Review emailer.py logs
- Verify EMAIL_FROM domain is verified in Resend

### Push notifications not working
- Verify VAPID keys are set
- Check PushSubscription exists for user
- Test with /push/test endpoint
- Review browser console for service worker errors

## Future Improvements (TODO)

- Rate limiting on API endpoints
- Comprehensive test suite (pytest)
- i18n/l10n support
- Advanced search filters (date range, etc.)
- User dashboard analytics
- Mobile app (React Native?)
- Webhook API for third-party integrations

---

**Last Updated:** 2026-07-07
**Project Status:** Production (self-hosted VPS)
**Primary Developer:** Solo project
