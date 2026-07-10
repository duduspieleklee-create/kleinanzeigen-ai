# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Changelog tracking for kleinanzeigen-ai.
- feat(mobile-qa): add dev-only quick-login route `/auth/dev/login-as/{user_id}` (#150) to enable screenshotting the authenticated dashboard on mobile without solving the Cloudflare Turnstile challenge (which can't load in headless/offline QA). Guarded to `ENVIRONMENT in (dev, test)` — returns 404 in production. Add `.turnstile-wrap` (clips the ~300px Turnstile iframe so it can't force horizontal scroll <360px) and `.field-col` (flex column that shrinks below its ideal width instead of overflowing at 320px) in `style.css`; replaced 4 inline `min-width:140px` on the admin search form with `.field-col`. Added `tests/test_mobile_qa_helpers.py`. Verified: route returns 303 + session cookie in dev, 404 in prod; full suite 26 passed. Note: the browser tool renders at 1280px so true 320–390px visual QA still needs a real device/emulator; the mobile-first CSS is verified statically.

### Fixed
- fix(auth): stop 500 on successful registration from non-ASCII flash cookies (#149). The `register` handler set `flash_success`/`flash_error` cookies with German copy containing `–`/`ü`/`ä`; Starlette encodes Set-Cookie as latin-1, so the response raised `UnicodeEncodeError` and turned every successful signup (SMTP configured) into a 500. Added `app/shared/cookies.py:ascii_cookie()` (transliterates umlauts, maps dashes, drops unmappable bytes) and routed every user-facing flash cookie through it in `auth.py`, `billing.py` and `scrapes.py`. Added `tests/test_flash_cookie_encoding.py`. Verified: registration now 303 + logged-in, full suite 24 passed.
- fix(migrations): resolve Alembic multi-head fork (#124). The slug chain `52ad6a85a96f` -> `a43ba04bf415` was stranded as a second head so `alembic upgrade heads` (run by `deploy/deploy.sh`) aborted and broke deploys. Added merge migration `5f17314ef463` joining both heads, and made `a43ba04bf415` idempotent (guards every drop/index/column) so re-running migrations is safe against a partially-applied DB.
- fix(security): remove hardcoded default admin password `KaSearch2026` from `config.py` (#125). `APP_PASSWORD` now has no built-in default; the bootstrap admin path stays disabled unless a strong password is supplied via env. The validator also rejects the old leaked value (public in git history) and any empty password when `BOOTSTRAP_ADMIN_ENABLED=true` outside dev. Rotate the credential on any live deployment.
- fix(security): back the rate limiter with Redis (#128). The slowapi `Limiter` used the default in-memory storage, so each API replica kept its own counters — an attacker got N auth attempts *per process*, defeating the brute-force throttle in multi-replica deploys. It now uses `storage_uri=settings.redis_url` for a shared window, with `in_memory_fallback_enabled=True` so a brief Redis outage degrades to per-process limiting instead of 500-ing every request. Storage init is lazy, so the CI import-smoke still runs without Redis.

### Added
- test(coverage): add real test suite + wire `pytest` into the CI `test` job (#127). Previously CI only did an import-smoke + `/healthz` check, so regressions like the #122 dashboard breakage went uncaught. New tests: `tests/test_dashboard_render.py` renders `dashboard.html` with the exact `_build_dashboard` context contract (catches Jinja parse/structure regressions), and `tests/test_billing_webhook.py` covers the Stripe webhook 503/400/idempotent-replay paths without hitting Stripe. Added `tests/conftest.py` (registers template globals) and `pytest.ini`; pinned `pytest` in `requirements.txt`.

### Fixed
- fix(ci): resolve `ModuleNotFoundError: No module named 'app'` failing the CI `test` job on every run. The `test` job invokes `pytest -q` as a console script, which does not add the repo root to `sys.path` (unlike `python -m pytest`, which is why it passed locally). `tests/conftest.py` does `import app.api.main`, so the job aborted at conftest import. Added `pythonpath = .` to `pytest.ini` so the repo root is always on the path regardless of launcher. Verified: `pytest -q` now runs 21 passed (exit 0).

### Changed
- Worker seller-info extraction now caches listing detail page HTML within one task runtime, reducing duplicate HTTP requests across repeated seller URLs. Added retry wrapper for flaky fetch/no-data paths and Sentry metrics for request count, cache hits, request duration, no-match occurrences, and fetch failures.
