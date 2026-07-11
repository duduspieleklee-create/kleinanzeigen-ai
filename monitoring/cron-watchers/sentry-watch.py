#!/usr/bin/env python3
"""
Sentry watcher for kleinanzeigen-ai / python-fastapi (EU region).

Runs on a schedule (cron). Pulls unresolved issues from the last 14d, classifies
each one with the repo's known error fingerprints, and opens a GitHub issue ONLY
for genuinely LIVE bugs. Infra bursts, dev-noise, and already-known-stale
fingerprints are skipped. A JSON state file dedupes so nothing is filed twice.

Designed to run with no_agent=True: it produces the exact report text on stdout.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---- config ----
REPO = "/opt/kleinanzeigen-ai"
ORG = "kleinanzeigen-ai"
PROJ = "python-fastapi"
BASE = "https://de.sentry.io/api/0"
STATE_FILE = Path("/root/.hermes/sentry-cron-state.json")
GH_REPO = "duduspieleklee-create/kleinanzeigen-ai"

# Skip rules: (matcher) -> (bucket, reason). Matched issues get NO GitHub issue.
SKIP_RULES = [
    # dev / test noise
    ("release=local", "DEV_NOISE", "release=local (dev/preview run, not prod)"),
    ("git_sha=local", "DEV_NOISE", "git_sha=local (dev run)"),
    ("ValueError: boom", "DEV_NOISE", "test_metrics_prom assertion-style noise"),
    ("OSError: [Errno 98] Address already in use", "DEV_NOISE", "metrics bind in dev run"),
    ("SQLite objects created in a thread", "DEV_NOISE", "local SQLite thread error"),
    ("no such table", "DEV_NOISE", "local SQLite missing table"),
    ("ModuleNotFoundError", "DEV_NOISE", "missing module in dev env"),
    ("Sentry test message", "DEV_NOISE", "manual test event"),
    ("TemplateSyntaxError", "DEV_NOISE", "template parse in dev run"),
    ("AssertionError", "DEV_NOISE", "test assertion failure"),
    ("UndefinedError: 'build_info'", "DEV_NOISE", "template var before deploy; fixed"),
    # infra bursts (self-heal on restart)
    ("connect to redis", "INFRA_BURST", "redis connection-refused storm"),
    ("Connection to Redis lost", "INFRA_BURST", "redis reconnect storm"),
    ("WorkerShutdown", "INFRA_BURST", "celery worker shutdown during restart"),
    ("Consumer: Cannot connect to redis", "INFRA_BURST", "redis down during deploy"),
    ("reconnect to the Celery redis result", "INFRA_BURST", "redis result backend storm"),
    ("Retry limit exceeded while trying to reconnect", "INFRA_BURST", "redis reconnect retries"),
    # known-stale fingerprints (fix already shipped per error-patterns doc)
    ("Permission denied: 'celerybeat-schedule'", "STALE", "fixed by #195 (schedule -> /tmp)"),
    ("MismatchingStateError", "STALE", "fixed by #199 (force https redirect_uri)"),
    ("got an unexpected keyword argument 'deal'", "STALE", "old _send_push_notifications signature"),
    ("OAuthError: invalid_grant", "INFRA_USER", "transient end-user OAuth flake"),
    ("CookieError: Control characters", "INFRA_USER", "transient bad cookie from scraper"),
    ("Disk usage at", "INFRA_NOISE", "disk threshold alert (one-off)"),
]


def classify(title, tags):
    """Return (bucket, reason) — bucket is SKIP_* or LIVE."""
    blob = title
    tag_str = " ".join(f"{k}={v}" for k, v in (tags or {}).items())
    hay = blob + " " + tag_str
    for needle, bucket, reason in SKIP_RULES:
        if needle.lower() in hay.lower():
            return bucket, reason
    # not matched by any skip rule -> treat as a genuine LIVE bug
    return "LIVE", "no skip rule matched; treat as live bug"


def sentry_get(token, path):
    import urllib.request
    req = urllib.request.Request(BASE + path, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def gh_issue_create(title, body):
    res = subprocess.run(
        ["gh", "issue", "create", "--repo", GH_REPO, "--title", title,
         "--body", body, "--label", "bug"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        return None, res.stderr.strip()
    return res.stdout.strip(), None


def main():
    # load token
    env = (Path(REPO) / ".env").read_text()
    token = None
    for line in env.splitlines():
        if line.startswith("SENTRY_AUTH_TOKEN="):
            token = line.split("=", 1)[1].strip()
    if not token:
        print("ERROR: SENTRY_AUTH_TOKEN not found in .env")
        sys.exit(1)

    # load state
    state = {}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())

    # fetch unresolved 14d
    issues = sentry_get(token,
        f"/projects/{ORG}/{PROJ}/issues/?query=is:unresolved&statsPeriod=14d&limit=50")

    now = datetime.now(timezone.utc)
    report = []
    report.append(f"Sentry watch {now.isoformat()} — unresolved(14d): {len(issues)}")

    created = 0
    skipped = 0
    for i in issues:
        sid = i["shortId"]
        title = i["title"]
        # tags
        tags = {}
        for t in i.get("tags", []) or []:
            if isinstance(t, dict) and "key" in t:
                tags[t["key"]] = t.get("value")
        bucket, reason = classify(title, tags)
        if bucket == "LIVE":
            if sid in state:
                report.append(f"  [LIVE known] {sid} {title[:60]} (issue {state[sid]})")
                continue
            # open github issue
            body = (
                f"Severity: HIGH\n\n"
                f"Location: Sentry issue {sid} — {PROJ}\n\n"
                f"Problem:\n{title}\n\n"
                f"count: {i.get('count')}  lastSeen: {i.get('lastSeen')}\n"
                f"culprit: {i.get('culprit')}\n\n"
                f"Fix: (to be investigated — auto-filed by sentry-watch cron)\n\n"
                f"Verification:\n- reproduce / confirm root cause\n"
                f"- deploy fix\n- confirm Sentry lastSeen predates deploy built_at\n\n"
                f"Auto-detected as LIVE by sentry-watch. "
                f"Tags: {tags}"
            )
            url, err = gh_issue_create(f"[SENTRY-LIVE] {title[:90]}", body)
            if url:
                state[sid] = url
                created += 1
                report.append(f"  [LIVE -> ISSUE] {sid} {title[:60]} -> {url}")
            else:
                report.append(f"  [LIVE CREATE FAIL] {sid} {title[:60]} :: {err}")
        else:
            skipped += 1
            report.append(f"  [{bucket}] {sid} {title[:50]} — {reason}")

    STATE_FILE.write_text(json.dumps(state, indent=2))
    if len(issues) == 0:
        # clean board -> one line so scheduled delivery isn't noisy
        print(f"Sentry watch {now.isoformat()}: 0 unresolved (14d) — clean.")
        return
    report.append(f"summary: created={created} skipped={skipped} total={len(issues)}")
    print("\n".join(report))


if __name__ == "__main__":
    main()
