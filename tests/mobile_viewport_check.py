#!/usr/bin/env python3
"""Mobile-viewport smoke test for the authenticated dashboard.

Boots against a running API, logs in via the dev-only quick-login route
(ENVIRONMENT must be dev/test so /auth/dev/login-as/<id> is enabled), loads
/dashboard at a 390px mobile viewport, and asserts there is no horizontal
overflow. Also captures a screenshot artifact.

This closes the gap from the mobile-first audit: the browser tool rendered at
1280px, so true 320-390px rendering was never verified automatically. Run by
the `mobile` CI job; can also be run locally against a live test server.

Usage:
    BASE_URL=http://127.0.0.1:8000 \
    DATABASE_URL=postgresql://... \
    python tests/mobile_viewport_check.py
"""
import os
import sys
import time
import argparse

# Ensure the repo root is importable when run as a script from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--viewport-width", type=int, default=390)
    parser.add_argument("--username", default="qa-mobile")
    parser.add_argument("--out", default=os.environ.get("GITHUB_WORKSPACE", "/tmp") + "/dashboard-mobile.png")
    args = parser.parse_args()

    # Create a verified user directly so we can use the dev quick-login route.
    from app.shared.database import SessionLocal, Base, engine
    from app.shared.models import User
    Base.metadata.create_all(bind=engine)  # no-op if tables exist (Postgres migrations ran)
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=args.username).first()
        if not user:
            user = User(username=args.username, email=f"{args.username}@example.com",
                        email_verified=True, is_active=True, hashed_password="x")
            db.add(user)
            db.commit()
        uid = user.id
    finally:
        db.close()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # Step 1: obtain a session cookie via the dev quick-login route.
            auth_ctx = browser.new_context()
            auth_pg = auth_ctx.new_page()
            resp = auth_pg.goto(f"{args.base_url}/auth/dev/login-as/{uid}", timeout=20000)
            if resp is None or resp.status >= 400:
                print(f"FAIL: dev login returned {resp.status if resp else 'no response'}")
                return 1
            cookies = auth_ctx.cookies()
            auth_ctx.close()

            # Step 2: load the dashboard at a mobile viewport with that cookie.
            ctx = browser.new_context(
                viewport={"width": args.viewport_width, "height": 844},
                is_mobile=True,
                has_touch=True,
                storage_state={"cookies": cookies},
            )
            pg = ctx.new_page()
            pg.goto(f"{args.base_url}/dashboard", timeout=20000)
            # Let JS-driven content (results fetch, tutorial modal) settle.
            pg.wait_for_timeout(2500)
            # Dismiss any onboarding modal so it doesn't skew the overflow read.
            pg.evaluate(
                "document.querySelectorAll('.tutorial-modal,.action-sheet,[role=dialog]').forEach(function (el){ el.remove(); });"
            )
            pg.wait_for_timeout(300)
            metrics = pg.evaluate(
                "({sw: document.documentElement.scrollWidth, iw: window.innerWidth, "
                "overflow: document.documentElement.scrollWidth - window.innerWidth})"
            )
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            pg.screenshot(path=args.out, full_page=False)
            ctx.close()

            print(f"MOBILE {args.viewport_width}px: scrollWidth={metrics['sw']} innerWidth={metrics['iw']} overflow={metrics['overflow']}")
            print(f"screenshot: {args.out}")
            if metrics["overflow"] > 1:
                print(f"FAIL: horizontal overflow of {metrics['overflow']}px at {args.viewport_width}px")
                return 1
            print("PASS: no horizontal overflow on mobile dashboard")
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
