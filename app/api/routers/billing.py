"""Stripe subscription billing — pricing page, checkout, webhook, portal.

Plans (see app/shared/plans.py):
  basic — free, 10 credits/week, 3 searches, 60-minute interval and up
  core  — paid, 50 credits/week, 10 searches, 30-minute interval and up
  pro   — paid, 150 credits/week, 25 searches, instant notifications (60 s checks)

First-time subscribers get a 3-day free trial on the Core plan: the checkout
collects a card but Stripe charges nothing until the trial ends. The trial is
once per account (users.trial_used, set by the webhook when a subscription
actually starts).

Prices themselves live in Stripe (STRIPE_PRICE_CORE / STRIPE_PRICE_PRO env vars
hold the recurring Price IDs), so amounts can be changed in the Stripe
dashboard without a code deploy.
"""
import logging
import time

import stripe
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.models import User
from app.shared.plans import (
    PLANS,
    enforce_plan_limits,
    ensure_weekly_credits,
    grant_plan,
)

logger = logging.getLogger("kleinanzeigen-ai")

router = APIRouter()
templates = Jinja2Templates(directory="app/api/templates")


def _billing_enabled() -> bool:
    # The webhook secret is required too: without it paid checkouts would
    # complete in Stripe but never be synced back to a plan upgrade here.
    return bool(
        settings.stripe_secret_key
        and settings.stripe_webhook_secret
        and settings.stripe_price_core
        and settings.stripe_price_pro
    )


CORE_TRIAL_DAYS = 3


def _trial_eligible(user) -> bool:
    """The Core trial is for first-time subscribers only."""
    return not user.trial_used and not user.stripe_subscription_id


def _price_to_plan(price_id: str) -> str | None:
    if price_id and price_id == settings.stripe_price_core:
        return "core"
    if price_id and price_id == settings.stripe_price_pro:
        return "pro"
    return None


def _base_url(request: Request) -> str:
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


# Cache the display prices fetched from Stripe so the pricing page does not
# call the Stripe API on every render. {plan: {"amount": int_cents, "currency": str}}
_price_cache: dict = {"at": 0.0, "prices": {}}
_PRICE_CACHE_TTL = 600  # seconds


def _display_prices() -> dict:
    """Fetch human-display prices from Stripe, cached for 10 minutes."""
    if not _billing_enabled():
        return {}
    now = time.time()
    if now - _price_cache["at"] < _PRICE_CACHE_TTL and _price_cache["prices"]:
        return _price_cache["prices"]
    prices = {}
    stripe.api_key = settings.stripe_secret_key
    for plan, price_id in (
        ("core", settings.stripe_price_core),
        ("pro", settings.stripe_price_pro),
    ):
        try:
            p = stripe.Price.retrieve(price_id)
            prices[plan] = {
                "amount": p["unit_amount"],
                "currency": (p["currency"] or "eur").upper(),
                "interval": (p.get("recurring") or {}).get("interval", "month"),
            }
        except Exception as e:
            logger.warning(f"Could not fetch Stripe price for {plan}: {e}")
    if prices:
        _price_cache["prices"] = prices
        _price_cache["at"] = now
    return prices


def _require_web_user(request: Request, db: Session):
    """Cookie-auth like the dashboard: redirect to login instead of a 401."""
    try:
        return get_current_user(
            request, token=request.cookies.get("access_token") or "", db=db
        )
    except HTTPException:
        return None


@router.get("/", name="pricing_page")
async def pricing_page(request: Request, db: Session = Depends(get_db)):
    # Public: a visitor without an account can see plans and prices before
    # signing up. Signed-in users additionally see their current plan,
    # credits, and subscription-aware CTAs (checkout vs. manage-billing).
    current = _require_web_user(request, db)
    user = None
    if current is not None:
        user = db.query(User).filter(User.id == current["id"]).first()
        ensure_weekly_credits(db, user)

    flash_success = request.cookies.get("flash_success")
    flash_error = request.cookies.get("flash_error")

    response = templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "plans": PLANS,
            "is_authenticated": user is not None,
            "current_plan": (user.plan or "basic") if user else None,
            "credits": user.credits if user else None,
            "billing_enabled": _billing_enabled(),
            "has_subscription": bool(user and user.stripe_subscription_id),
            "trial_eligible": bool(user) and _billing_enabled() and _trial_eligible(user),
            "trial_days": CORE_TRIAL_DAYS,
            "display_prices": _display_prices(),
            "flash_success": flash_success,
            "flash_error": flash_error,
        },
    )
    if flash_success:
        response.delete_cookie("flash_success")
    if flash_error:
        response.delete_cookie("flash_error")
    return response


@router.post("/checkout")
async def create_checkout(
    request: Request,
    plan: str = Form(...),
    db: Session = Depends(get_db),
):
    current = _require_web_user(request, db)
    if current is None:
        return RedirectResponse(url="/", status_code=303)

    if plan not in ("core", "pro"):
        return _flash_redirect("/billing", error="Unknown plan.")
    if not _billing_enabled():
        return _flash_redirect(
            "/billing", error="Billing is not configured yet. Please try again later."
        )

    user = db.query(User).filter(User.id == current["id"]).first()
    price_id = (
        settings.stripe_price_core if plan == "core" else settings.stripe_price_pro
    )

    stripe.api_key = settings.stripe_secret_key

    # Existing subscribers must change plans through the billing portal —
    # a fresh Checkout would create a second, overlapping subscription and
    # double-bill them.
    if user.stripe_subscription_id:
        try:
            session = stripe.billing_portal.Session.create(
                customer=user.stripe_customer_id,
                return_url=f"{_base_url(request)}/billing",
            )
            return RedirectResponse(url=session["url"], status_code=303)
        except Exception as e:
            logger.error(f"Stripe portal (plan switch) failed for user {user.id}: {e}")
            return _flash_redirect(
                "/billing",
                error="You already have a subscription - use Manage billing to switch plans.",
            )

    try:
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email if "@" in (user.email or "") else None,
                metadata={"user_id": str(user.id), "username": user.username},
            )
            user.stripe_customer_id = customer["id"]
            db.commit()

        # 3-day Core trial for first-time subscribers: the card is collected
        # up front but nothing is charged until the trial ends. Eligibility
        # is burned only when a subscription actually starts (webhook), so an
        # abandoned checkout keeps the trial available.
        subscription_data = {"metadata": {"user_id": str(user.id), "plan": plan}}
        if plan == "core" and _trial_eligible(user):
            subscription_data["trial_period_days"] = CORE_TRIAL_DAYS

        base = _base_url(request)
        session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base}/billing/success",
            cancel_url=f"{base}/billing",
            metadata={"user_id": str(user.id), "plan": plan},
            subscription_data=subscription_data,
            allow_promotion_codes=True,
        )
    except Exception as e:
        logger.error(f"Stripe checkout failed for user {user.id}: {e}")
        return _flash_redirect(
            "/billing", error="Could not start checkout. Please try again."
        )

    return RedirectResponse(url=session["url"], status_code=303)


@router.get("/success")
async def checkout_success():
    return _flash_redirect(
        "/dashboard",
        success="Payment received - your plan will be upgraded within a few seconds.",
    )


@router.post("/portal")
async def billing_portal(request: Request, db: Session = Depends(get_db)):
    current = _require_web_user(request, db)
    if current is None:
        return RedirectResponse(url="/", status_code=303)

    user = db.query(User).filter(User.id == current["id"]).first()
    if not user.stripe_customer_id or not settings.stripe_secret_key:
        return _flash_redirect("/billing", error="No billing account found.")

    stripe.api_key = settings.stripe_secret_key
    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{_base_url(request)}/billing",
        )
    except Exception as e:
        logger.error(f"Stripe portal failed for user {user.id}: {e}")
        return _flash_redirect(
            "/billing", error="Could not open the billing portal. Please try again."
        )
    return RedirectResponse(url=session["url"], status_code=303)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe events keep the local plan state in sync.

    Handled events:
      checkout.session.completed      -> upgrade the user, grant credits
      customer.subscription.updated   -> plan change / cancellation state
      customer.subscription.deleted   -> downgrade to basic
    """
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        user_id = (obj.get("metadata") or {}).get("user_id")
        plan = (obj.get("metadata") or {}).get("plan")
        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            logger.warning(f"Billing webhook: bad user_id metadata {user_id!r}")
            user_id_int = None
        user = (
            db.query(User).filter(User.id == user_id_int).first()
            if user_id_int is not None
            else None
        )
        if user and plan in ("core", "pro"):
            user.stripe_customer_id = obj.get("customer") or user.stripe_customer_id
            user.stripe_subscription_id = (
                obj.get("subscription") or user.stripe_subscription_id
            )
            # Any started subscription (trialing or not) ends first-time
            # eligibility for the Core trial.
            user.trial_used = True
            grant_plan(db, user, plan)
            enforce_plan_limits(db, user)
            logger.info(f"Billing: user {user.id} upgraded to {plan}")

    elif etype == "customer.subscription.updated":
        user = (
            db.query(User)
            .filter(User.stripe_customer_id == obj.get("customer"))
            .first()
        )
        if user:
            status = obj.get("status")
            items = (obj.get("items") or {}).get("data") or []
            price_id = items[0]["price"]["id"] if items else ""
            plan = _price_to_plan(price_id)
            if status in ("active", "trialing") and plan and plan != user.plan:
                user.stripe_subscription_id = obj.get("id")
                user.trial_used = True  # backstop if the checkout webhook was missed
                grant_plan(db, user, plan)
                # Plan switches include downgrades (pro -> core): sweep any
                # recurring searches that exceed the new plan's limits.
                enforce_plan_limits(db, user)
                logger.info(f"Billing: user {user.id} switched to {plan}")
            elif status in ("canceled", "unpaid", "incomplete_expired"):
                user.plan = "basic"
                user.stripe_subscription_id = None
                db.commit()
                enforce_plan_limits(db, user)
                logger.info(f"Billing: user {user.id} downgraded (status={status})")

    elif etype == "customer.subscription.deleted":
        user = (
            db.query(User)
            .filter(User.stripe_customer_id == obj.get("customer"))
            .first()
        )
        if user:
            user.plan = "basic"
            user.stripe_subscription_id = None
            db.commit()
            enforce_plan_limits(db, user)
            logger.info(f"Billing: user {user.id} subscription ended -> basic")

    return JSONResponse({"received": True})


def _flash_redirect(url: str, success: str = None, error: str = None):
    # Flash cookie values must stay ASCII — Starlette encodes Set-Cookie
    # headers as latin-1 and non-ASCII raises at response time.
    response = RedirectResponse(url=url, status_code=303)
    if success:
        response.set_cookie("flash_success", success, max_age=10)
    if error:
        response.set_cookie("flash_error", error, max_age=10)
    return response
