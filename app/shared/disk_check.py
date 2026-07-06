"""Disk-usage alert, run periodically via host cron (see docs/vps-deployment.md).

Checked from inside the api container rather than the host directly: the
container's overlay root and the host's postgres_data volume live on the
same underlying filesystem, so shutil.disk_usage("/") here reports the same
totals as `df /` on the host, and this way the alert reuses the already
-configured Sentry SDK instead of re-implementing its wire protocol in shell.

Usage: python -m app.shared.disk_check [threshold_percent] [path]
"""
import shutil
import sys

import sentry_sdk

from app.shared.sentry import init_sentry

DEFAULT_THRESHOLD_PERCENT = 85.0
DEFAULT_PATH = "/"


def main() -> None:
    threshold = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_THRESHOLD_PERCENT
    path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PATH

    total, used, _free = shutil.disk_usage(path)
    pct_used = used / total * 100

    if pct_used >= threshold:
        init_sentry("disk-check")
        sentry_sdk.capture_message(
            f"Disk usage at {pct_used:.1f}% on {path} (threshold {threshold:.0f}%)",
            level="warning",
        )
        print(f"ALERT sent: {pct_used:.1f}% used (threshold {threshold:.0f}%)")
    else:
        print(f"OK: {pct_used:.1f}% used (threshold {threshold:.0f}%)")


if __name__ == "__main__":
    main()
