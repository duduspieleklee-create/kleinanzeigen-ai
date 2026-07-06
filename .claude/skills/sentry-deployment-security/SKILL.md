---
name: sentry-deployment-security
description: Use when adding/checking Sentry error tracking or custom Application Metrics in this repo, or before/after any live-deployment change (docker-compose.prod.yml edits, new containers, opening ports, cron/infra changes). Covers the init_sentry() pattern, what's worth instrumenting vs. noise, user-facing vs. internal error messages, and the ufw+Docker port-exposure checklist. Triggers: "add sentry", "error tracking", "application metrics", "track this failure", "harden deployment", "check firewall", "is this port exposed", "before we go live".
---

# Sentry & Live-Deployment Security

Distilled from actually wiring this up in kleinanzeigen-ai, including a real
finding (an unrelated project on the same VPS had Chrome DevTools Protocol
open to the internet — see part 3).

## 1. Installing & initializing Sentry

Pattern used here (`app/shared/sentry.py`):

```python
def init_sentry(component: str) -> None:
    if not settings.sentry_dsn:
        return
    if settings.environment == "dev" and not settings.sentry_enable_in_dev:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.git_sha,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    sentry_sdk.set_tag("component", component)
```

- Call it once per process, as early as possible in each service's entry
  point (`app/api/main.py`, `app/worker/celery_app.py`, `app/beat/celery_beat.py`),
  each tagged with its own `component` name so events are filterable by service.
- No-op if the DSN is unset, and no-op in dev unless explicitly re-enabled —
  otherwise local development spams the project with noise.
- Settings live in `app/shared` config as plain `pydantic` fields
  (`sentry_dsn`, `sentry_enable_in_dev`, `sentry_traces_sample_rate`) — never
  hardcode a DSN in source.
- **After changing `SENTRY_DSN` or any `.env` value**, a `restart` is not
  enough on a no-bind-mount prod compose (`docker-compose.prod.yml`): env
  vars are baked in at container creation. Use
  `docker compose -f docker-compose.prod.yml up -d <service>` (recreate),
  not `restart`, and rebuild first (`docker compose build <service>`) if code
  changed too.
- Verify: `docker compose logs <service> --since 30s | grep -i sentry` should
  show `Sentry error tracking enabled for component=<x>`.

## 2. What's worth tracking (vs. noise)

**Automatic and free once `init()` runs**: unhandled exceptions in
FastAPI/Starlette routes and Celery tasks, via auto-detected integrations,
tagged with `release=git_sha`.

**Explicit capture is required for anything your own code already catches.**
Celery's `task_failure` signal (and therefore Sentry's Celery integration)
only fires when retries are exhausted — an exception caught, logged, and
retried via `self.retry(...)` is invisible to Sentry on every attempt except
the last unless you call `sentry_sdk.capture_exception()` yourself:

```python
sentry_sdk.capture_exception(
    exc,
    tags={"task_id": str(task_id), "attempt": str(attempt)},
    contexts={"scrape": {"task_id": task_id, "keywords": ..., "url": ...}},
)
```

Also: `logger.error("...")` alone *does* create a Sentry event via the
default logging integration (level ≥ ERROR is auto-captured) but without a
real traceback unless you pass `exc_info=True`. Don't rely on bare
`logger.error` when you actually want to debug this later.

**Custom Application Metrics** (`sentry_sdk.metrics.count/gauge/distribution`
— enabled by default in sentry-sdk ≥2.x, verify via
`sentry_sdk.utils.has_metrics_enabled` if unsure for the installed version).
Good candidates, established in `app/shared/metrics.py`'s `track_job()`:

- **Job lifecycle** for every background/cron task: `job.started`,
  `job.completed`/`job.failed` counters + `job.duration_ms` distribution,
  tagged by job name. One small context manager avoids repeating this per task.
- **Business volume**: units processed per run (e.g. `scrape.listings_found`),
  notifications sent/failed by channel. A silently-broken schedule shows up
  as a "0 dispatched" data point long before anyone notices missing output.
- **Naming**: dot-namespaced, tag by job/task name and other *low-cardinality*
  dimensions only. Never put raw user IDs, emails, or other high-cardinality/
  PII values in `tags` (they're indexed and enumerable) — put those in
  `contexts`/`extras` instead, which are stored per-event but not used for
  faceting.

**User-facing errors are a separate, shorter message than what Sentry gets.**
Don't show users tracebacks. Classify the exception into a short string
(timeout / rate-limited / server error / unknown) and store *that* on the
domain record (e.g. `ScrapeTask.error_message`); keep full detail in Sentry
only. Clear the stored message on the next success so stale failures don't
linger in the UI.

## 3. Securing the environment for live deployment

Config-level guardrail already in this repo (`app/api/config.py`): fail
startup outside `dev` if secrets are still default/weak
(`_reject_insecure_defaults_in_prod`). Apply the same pattern to any new
prod-only credential.

**Port-exposure checklist — run this on the whole VPS, not just the project
you're touching.** `ufw status` alone is not sufficient and can be actively
misleading:

1. `ufw status verbose` — shows what you *intended* to allow.
2. Docker inserts its own iptables/nftables rules ahead of ufw's chain, so
   any compose `ports: "HOST:CONTAINER"` mapping *without* an explicit bind
   address publishes to `0.0.0.0` and **bypasses ufw entirely**. Check
   `iptables -L DOCKER-USER -n -v` — if empty, ufw is not filtering
   container ports at all, regardless of what `ufw status` claims.
3. Ground truth, always, across **every** docker-compose project on the
   host (other people's/your own other projects on the same box are exactly
   as reachable as the one you're working on):
   ```
   docker ps --format 'table {{.Names}}\t{{.Ports}}'
   ss -tlnp
   ```
   `0.0.0.0` / `:::` = internet-reachable. `127.0.0.1` = local-only. Trust
   `ss`, not the compose file, as the final check after any change.
4. Only bind host ports a service actually needs public. Everything else
   (dashboards, debug ports, internal APIs) gets an explicit bind address:
   `"127.0.0.1:PORT:PORT"`, never bare `"PORT:PORT"`. Use an SSH tunnel
   (`ssh -L PORT:localhost:PORT host`) for occasional remote access instead
   of opening the port.
5. Treat any debug/inspection protocol as never-publicly-exposed by
   default — it typically has no auth of its own. Concretely found on this
   VPS: Chrome DevTools Protocol (port 9222) open to `0.0.0.0` from an
   unrelated project, which would let anyone on the internet read
   cookies/session tokens and run arbitrary JS in that browser.
6. Flag `privileged: true` on any container even if not asked — it grants
   near-root-on-host capabilities and raises the severity of every other
   finding in that container.

**Sentry-specific:**
- Leave `send_default_pii` at its default `False` unless you specifically
  need it and have a redaction/`before_send` strategy — otherwise user
  emails/IPs land in every event.
- Keep `traces_sample_rate` low/0 in prod unless performance monitoring is
  actively used; full tracing has real cost and volume.
- A DSN is a write-only ingest key, not a read secret — but still don't
  hardcode it in source, and rotate it if it ends up in a public repo.

## Verification checklist after any Sentry or deployment change

- [ ] Rebuilt + recreated (not just restarted) containers if code/env changed
      on a no-bind-mount prod compose
- [ ] `docker compose logs <service> --since Xs | grep -i sentry` shows init
- [ ] Forced one real failure path (throwaway record) to confirm it reaches
      Sentry with the expected tags/context, then cleaned up the test data
- [ ] `ss -tlnp` after any port-binding change, on the whole host
- [ ] `alembic current` matches head if a migration was involved
- [ ] Any recreate/restart/migration/crontab/firewall change against a live
      deployment was confirmed with the user first — these are exactly the
      hard-to-reverse, shared-state actions worth pausing on
