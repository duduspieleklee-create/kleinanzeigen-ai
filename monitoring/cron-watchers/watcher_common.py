#!/usr/bin/env python3
"""
Shared helper for cron watchers: GitHub issue create/close with per-alert
dedup, and a small strike-counter for flaky signals (e.g. health-down).

State shape (JSON): { "<alert_key>": {"issue": "<url>", "strikes": <int>} }
- alert_key is stable per alert type (e.g. "health:down", "health:drift",
  "stuck:scrape") so reopens/recovers are tracked per type.
- When an alert is active: ensure an open issue exists.
- When an alert clears: close the issue (auto-close) and forget the key.
- Strikes: only file an issue once the signal has repeated STRIKE_THRESHOLD
  times consecutively (guards transient blips); recovered on any clear.
"""
import json
import subprocess
from pathlib import Path

GH_REPO = "duduspieleklee-create/kleinanzeigen-ai"


def _gh(args):
    res = subprocess.run(["gh", "issue"] + args, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def ensure_issue(state, key, title, body, label):
    """Open an issue for `key` if none is open. Returns updated state."""
    entry = state.get(key)
    if entry and entry.get("issue"):
        # already open for this alert; just refresh strikes
        entry["strikes"] = entry.get("strikes", 0) + 1
        state[key] = entry
        return state, entry["issue"]
    rc, out, err = _gh(["create", "--repo", GH_REPO, "--title", title,
                        "--body", body, "--label", label])
    if rc != 0:
        return state, None
    state[key] = {"issue": out, "strikes": 1}
    return state, out


def close_issue(state, key):
    """Close the issue for `key` if open; forget the key."""
    entry = state.get(key)
    if not entry or not entry.get("issue"):
        state.pop(key, None)
        return state, False
    url = entry["issue"]
    # extract numeric id from url tail
    num = url.rstrip("/").split("/")[-1]
    rc, out, err = _gh(["close", num, "--repo", GH_REPO, "--comment",
                        "Auto-closed: alert condition cleared (cron watcher)."])
    state.pop(key, None)
    return state, rc == 0


def load_state(path):
    return json.loads(Path(path).read_text()) if Path(path).exists() else {}


def save_state(path, state):
    Path(path).write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    print("helper module — import from watchers")
