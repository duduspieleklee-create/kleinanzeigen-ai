#!/usr/bin/env python3
"""
Health + deploy-drift probe for kleeblatt.space (kleinanzeigen-ai).

Cron (no_agent). Hits /healthz and /version, compares deployed SHA to local
HEAD. On a real problem it opens a GitHub issue (deduped per alert type);
when the problem clears it auto-closes the issue (watcher_common.close_issue).

Alert types:
  health:down  -> healthz unreachable/non-200. Flaky guard: file only after
                  STRIKE_THRESHOLD consecutive failures (default 2) so a 10s
                  blip doesn't open an issue.
  health:drift -> live commit != local HEAD. Filed immediately.
"""
import json
import subprocess
import urllib.request
from datetime import datetime, timezone

import watcher_common as wc

HOST = "https://kleeblatt.space"
REPO = "/opt/kleinanzeigen-ai"
STATE_FILE = "/root/.hermes/sentry-cron-state.json"  # shared dedup store
TIMEOUT = 15
STRIKE_THRESHOLD = 2
GH_LABEL = "bug"


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-health-probe/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, json.load(r)


def git_head():
    out = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def main():
    now = datetime.now(timezone.utc).isoformat()
    state = wc.load_state(STATE_FILE)
    problems = []

    # healthz
    try:
        status, _ = http_get_json(f"{HOST}/healthz")
        if status != 200:
            problems.append(("health:down", f"/healthz returned HTTP {status} (expected 200)"))
    except Exception as e:
        problems.append(("health:down", f"/healthz unreachable: {e}"))

    # version + drift
    deployed = built_at = None
    try:
        status, ver = http_get_json(f"{HOST}/version")
        if status == 200 and isinstance(ver, dict):
            deployed, built_at = ver.get("commit"), ver.get("built_at")
        else:
            problems.append(("health:down", f"/version returned HTTP {status}"))
    except Exception as e:
        problems.append(("health:down", f"/version unreachable: {e}"))

    head = git_head()
    if deployed and head and deployed != head:
        problems.append(("health:drift",
            f"live commit {deployed[:10]} != HEAD {head[:10]} (stale build)"))

    active_keys = {k for k, _ in problems}

    # auto-close recovered alerts (not in active set)
    for key in list(state.keys()):
        if key.startswith("health:") and key not in active_keys:
            state, _ = wc.close_issue(state, key)

    if not problems:
        wc.save_state(STATE_FILE, state)
        print(f"health probe {now}: OK (healthz=200, deploy={deployed[:10] if deployed else '?'}, built_at={built_at})")
        return

    # file/keep issues; apply strike guard for health:down
    for key, detail in problems:
        strikes = state.get(key, {}).get("strikes", 0) + 1
        if key == "health:down" and strikes < STRIKE_THRESHOLD:
            state.setdefault(key, {"issue": None, "strikes": 0})
            state[key]["strikes"] = strikes
            print(f"health probe {now}: {key} strike {strikes}/{STRIKE_THRESHOLD} ({detail}) — not yet filed")
            continue
        title = f"[CRON-ALERT] {key}: {detail[:80]}"
        body = (f"Severity: HIGH\n\nLocation: kleeblatt.space health probe\n\n"
                f"Problem:\n{detail}\n\n"
                f"detected: {now}\ndeployed_commit: {deployed}\nbuilt_at: {built_at}\nlocal_HEAD: {head}\n\n"
                f"Fix: investigate VPS container / recent deploy / CI 'deploy' job.\n\n"
                f"Auto-filed by health-probe cron; auto-closes when condition clears.")
        state, url = wc.ensure_issue(state, key, title, body, GH_LABEL)
        if url:
            print(f"health probe {now}: PROBLEM {key} -> issue {url} ({detail})")
        else:
            print(f"health probe {now}: PROBLEM {key} (issue create FAILED) ({detail})")
    wc.save_state(STATE_FILE, state)


if __name__ == "__main__":
    main()
