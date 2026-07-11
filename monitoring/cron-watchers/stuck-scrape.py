#!/usr/bin/env python3
"""
Stuck-scrape detection for kleinanzeigen-ai (Postgres inside docker).

Cron (no_agent). Read-only SELECT on scrape_tasks for tasks stuck
status='running' with no progress > STUCK_MINUTES. On stuck tasks it opens a
GitHub issue (deduped per alert type); when none are stuck it auto-closes the
issue (watcher_common.close_issue). Runs psql INSIDE the db container via
docker compose exec — no host port / psycopg2 needed.

Alert type: stuck:scrape
"""
import subprocess
from datetime import datetime, timezone

import watcher_common as wc

REPO = "/opt/kleinanzeigen-ai"
STATE_FILE = "/root/.hermes/sentry-cron-state.json"  # shared dedup store
STUCK_MINUTES = 30
ALERT_KEY = "stuck:scrape"
GH_LABEL = "bug"

QUERY = """
SELECT id, user_id, status, last_run_at, created_at
FROM scrape_tasks
WHERE status = 'running'
  AND (COALESCE(last_run_at, created_at)) < (NOW() - INTERVAL '%d minutes')
ORDER BY COALESCE(last_run_at, created_at) ASC;
""" % STUCK_MINUTES


def psql_exec(sql):
    res = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql",
         "-U", "kleinanzeigen", "-d", "kleinanzeigen_ai",
         "-t", "-A", "-F", "\t", "-c", sql],
        cwd=REPO, capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip() or "psql exited non-zero")
    rows = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("SELECT") or line.startswith("Time"):
            continue
        rows.append(line.split("\t"))
    return rows


def main():
    now = datetime.now(timezone.utc)
    state = wc.load_state(STATE_FILE)
    try:
        rows = psql_exec(QUERY)
    except Exception as e:
        print(f"stuck-scrape {now.isoformat()}: DB QUERY FAILED: {e}")
        return

    if not rows:
        # recover -> auto-close
        if state.get(ALERT_KEY, {}).get("issue"):
            state, closed = wc.close_issue(state, ALERT_KEY)
            print(f"stuck-scrape {now.isoformat()}: OK (cleared, auto-closed alert)")
        else:
            print(f"stuck-scrape {now.isoformat()}: OK (no tasks stuck >{STUCK_MINUTES}min)")
        wc.save_state(STATE_FILE, state)
        return

    detail = f"{len(rows)} task(s) stuck >{STUCK_MINUTES}min: " + ", ".join(
        f"id={r[0]}(user={r[1]})" for r in rows[:10])
    body = (f"Severity: HIGH\n\nLocation: scrape_tasks (status='running')\n\n"
            f"Problem:\n{detail}\n\n"
            f"detected: {now}\n\n"
            f"Fix: worker likely died mid-run (redis/db outage in same window?). "
            f"Reap via reaper or restart worker.\n\n"
            f"Auto-filed by stuck-scrape cron; auto-closes when no tasks are stuck.")
    title = f"[CRON-ALERT] {ALERT_KEY}: {len(rows)} stuck task(s)"
    state, url = wc.ensure_issue(state, ALERT_KEY, title, body, GH_LABEL)
    if url:
        print(f"stuck-scrape {now.isoformat()}: PROBLEM -> issue {url} ({len(rows)} stuck)")
    else:
        print(f"stuck-scrape {now.isoformat()}: PROBLEM (issue create FAILED) ({len(rows)} stuck)")
    wc.save_state(STATE_FILE, state)


if __name__ == "__main__":
    main()
