"""Tests for the Stripe billing webhook endpoint (#127).

Covers the parts that don't require a live Stripe call:
- 503 when the webhook secret is not configured
- 400 on an invalid signature (stripe.Webhook.construct_event raises)
- 200 + idempotent skip when the same event_id is replayed

The route validates the signature via stripe.Webhook.construct_event, which is
monkeypatched here so we never hit Stripe's network. The route is async, so each
test drives it via asyncio.run() (no pytest-asyncio dependency required).
"""
import asyncio
import json
from unittest.mock import MagicMock, patch

import stripe

import pytest
from fastapi import HTTPException

import app.api.config as config_mod
import app.api.routers.billing as billing


def _make_request(payload: dict, signature: str = "sig") -> MagicMock:
    req = MagicMock()
    # Starlette's Request.body() is a coroutine; mirror that.
    async def _body():
        return json.dumps(payload).encode()
    req.body = _body
    req.headers = {"stripe-signature": signature}
    return req


def test_webhook_503_when_secret_unset():
    """With no webhook secret configured the route refuses to run."""
    saved = config_mod.settings.stripe_webhook_secret
    config_mod.settings.stripe_webhook_secret = ""
    try:
        with pytest.raises(HTTPException) as exc:
            # db arg is unused before the secret check
            asyncio.run(billing.stripe_webhook(_make_request({"type": "x"}), db=MagicMock()))
        assert exc.value.status_code == 503
    finally:
        config_mod.settings.stripe_webhook_secret = saved


def test_webhook_400_on_bad_signature():
    """An invalid signature must yield a 400, never a 500."""
    saved = config_mod.settings.stripe_webhook_secret
    config_mod.settings.stripe_webhook_secret = "whsec_test"
    try:
        with patch(
            "app.api.routers.billing.stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad sig", "sig"),
        ):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(billing.stripe_webhook(_make_request({"type": "x"}), db=MagicMock()))
        assert exc.value.status_code == 400
    finally:
        config_mod.settings.stripe_webhook_secret = saved


def test_webhook_idempotent_replay():
    """Replaying an already-processed event_id returns 200 and skips work.

    We set stripe_webhook_secret and make construct_event return a valid event,
    then force _already_processed() to True so the handler short-circuits.
    """
    saved = config_mod.settings.stripe_webhook_secret
    config_mod.settings.stripe_webhook_secret = "whsec_test"
    try:
        event = {"id": "evt_replay_1", "type": "checkout.session.completed",
                 "data": {"object": {"id": "cs_1"}}}
        with patch(
            "app.api.routers.billing.stripe.Webhook.construct_event",
            return_value=event,
        ), patch.object(billing, "_already_processed", return_value=True):
            resp = asyncio.run(billing.stripe_webhook(_make_request(event), db=MagicMock()))
        assert resp.status_code == 200
        assert json.loads(resp.body)["received"] is True
    finally:
        config_mod.settings.stripe_webhook_secret = saved
