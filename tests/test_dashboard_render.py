"""Regression test for the dashboard template render (#122).

Renders app/api/templates/dashboard.html with the exact context contract
produced by _build_dashboard() in app/api/main.py. If the template regresses
to a Jinja parse error or references an undefined global, this fails loudly —
catching the class of breakage that took /dashboard down with a 500 after
login.

Uses the project's own Jinja2Templates instance (app.api.main.templates), so
the globals (build_info, turnstile_site_key) are identical to production.
"""
from unittest.mock import MagicMock


import app.api.main as main


def _context(is_admin: bool = False):
    """Minimal but type-correct context mirroring _build_dashboard's contract."""
    # A fake request is enough — templates only need .url / __class__ for macros.
    request = MagicMock()
    request.url = "http://testserver/dashboard"

    user = MagicMock()
    user.id = 1
    user.is_admin = is_admin
    user.email = "tester@example.com"
    user.email_verified = True
    user.has_completed_tutorial = True
    user.plan = "basic"
    user.plan_notice = None
    user.credits = 0
    user.credits_reset_at = None

    task = MagicMock()
    task.id = 1
    task.result_count = 0
    task.parameters = {"keywords": "fahrrad"}
    task.status = "completed"
    task.created_at = None

    result = MagicMock()
    result.id = 1
    result.price_value = 100
    result.price = "100 €"
    result.title = "Fahrrad"
    result.location = "Berlin"
    result.description = "Gut erhalten"
    result.trust_score = 80  # real int so the trust-pill comparison works
    result.deal = None
    result.search_keywords = "fahrrad"
    result.relative_time = "gerade eben"
    result.is_new = True
    result.created_at = None

    return {
        "request": request,
        "tasks": [task],
        "recent_results": [result],
        "show_deals": is_admin,
        "show_trust_scores": is_admin,
        "flash_success": None,
        "flash_error": None,
        "new_task_id": None,
        "plan_notice": None,
        "is_admin": is_admin,
        "admin_searches": [],
        "proxies": [],
        "rotating_proxy_enabled": False,
        "admin_error": None,
        "proxy_error": None,
        "plan_name": "basic",
        "plan_label": "Basic",
        "credits": 0,
        "credits_reset_at": None,
        "active_searches": 0,
        "max_active_searches": 1,
        "min_interval_seconds": 5 if is_admin else 300,
        "email_verified": True,
        "user_email": "tester@example.com",
        "show_tutorial": False,
        "token_stats": {"last_24h": 0, "last_7d": 0, "total": 0, "by_task": []},
        "favorites": [],
    }


class TestDashboardRender:
    def test_dashboard_renders_for_regular_user(self):
        """A non-admin user context must render without raising."""
        html = main.templates.get_template("dashboard.html").render(**_context(False))
        assert "<!DOCTYPE html>" in html or "<html" in html
        assert "Meine Suchen" in html  # a known German heading in the template

    def test_dashboard_renders_for_admin(self):
        """Admin context (proxies / admin searches tabs) must render too."""
        html = main.templates.get_template("dashboard.html").render(**_context(True))
        assert "Admin" in html

    def test_dashboard_has_no_undefined_globals(self):
        """Render must not leak 'undefined' markers from Jinja globals."""
        html = main.templates.get_template("dashboard.html").render(**_context(False))
        # {{ Undefined }}-style debug output would indicate a missing global.
        assert "Undefined" not in html

    def test_wizard_step2_sells_automation(self):
        """Step 2 must make the recurring/auto-search value prop explicit
        (the differentiator vs kleinanzeigen.de's one-time search)."""
        html = main.templates.get_template("dashboard.html").render(**_context(False))
        assert "Automatisierung" in html          # step-2 indicator label
        assert "Jetzt automatisieren" in html      # step-2 header title
        assert "immer wieder automatisch" in html  # differentiator copy
