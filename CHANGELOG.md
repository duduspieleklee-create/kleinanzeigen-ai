# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Changelog tracking for kleinanzeigen-ai.

### Fixed
- fix(migrations): resolve Alembic multi-head fork (#124). The slug chain `52ad6a85a96f` -> `a43ba04bf415` was stranded as a second head so `alembic upgrade heads` (run by `deploy/deploy.sh`) aborted and broke deploys. Added merge migration `5f17314ef463` joining both heads, and made `a43ba04bf415` idempotent (guards every drop/index/column) so re-running migrations is safe against a partially-applied DB.
- fix(security): remove hardcoded default admin password `KaSearch2026` from `config.py` (#125). `APP_PASSWORD` now has no built-in default; the bootstrap admin path stays disabled unless a strong password is supplied via env. The validator also rejects the old leaked value (public in git history) and any empty password when `BOOTSTRAP_ADMIN_ENABLED=true` outside dev. Rotate the credential on any live deployment.

### Added
- test(coverage): add real test suite + wire `pytest` into the CI `test` job (#127). Previously CI only did an import-smoke + `/healthz` check, so regressions like the #122 dashboard breakage went uncaught. New tests: `tests/test_dashboard_render.py` renders `dashboard.html` with the exact `_build_dashboard` context contract (catches Jinja parse/structure regressions), and `tests/test_billing_webhook.py` covers the Stripe webhook 503/400/idempotent-replay paths without hitting Stripe. Added `tests/conftest.py` (registers template globals) and `pytest.ini`; pinned `pytest` in `requirements.txt`.

### Changed
- Worker seller-info extraction now caches listing detail page HTML within one task runtime, reducing duplicate HTTP requests across repeated seller URLs. Added retry wrapper for flaky fetch/no-data paths and Sentry metrics for request count, cache hits, request duration, no-match occurrences, and fetch failures.
