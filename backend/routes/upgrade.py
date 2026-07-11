from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import stripe
import os
from typing import Optional, List

router = APIRouter(prefix="/upgrade", tags=["upgrade"])

# Stripe-Client initialisieren
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@router.post("/checkout/create-session")
async def create_checkout_session(
    request: Request,
    plan: str = "basic",
    paymentMethod: str = "card",  # Stripe erwartet "card" statt "stripe"
    successUrl: Optional[str] = None,
    cancelUrl: Optional[str] = None
):
    """
    Erstelle eine Stripe-Checkout-Session für den Upgrade-Pfad.
    
    Args:
        plan: "basic", "pro" oder "business"
        paymentMethod: "card" (Kreditkarte), "paypal", "crypto" oder "sepa"
        successUrl: Erfolg-URL nach Checkout
        cancelUrl: Abbruch-URL
    
    Returns:
        JSON mit sessionId und URL
    """
    if plan not in ["basic", "pro", "business"]:
        raise HTTPException(status_code=400, detail="Ungültiger Plan")
    if paymentMethod not in ["card", "paypal", "crypto", "sepa"]:
        raise HTTPException(status_code=400, detail="Ungültige Zahlungsmethode")

    # Preise in Cent (Stripe erwartet Integer)
    price_map = {
        "basic": 499,
        "pro": 999,
        "business": 1999
    }
    price_id = price_map.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Preis nicht gefunden")

    # Standard-URLs, falls nicht angegeben
    base_success_url = successUrl or f"{request.url.scheme}://{request.url.netloc}/dashboard?upgrade=success"
    base_cancel_url = cancelUrl or f"{request.url.scheme}://{request.url.netloc}/dashboard?upgrade=cancel"

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=[paymentMethod],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": f"Core {plan.capitalize()}",
                    },
                    "unit_amount": price_id,
                    "recurring": {
                        "interval": "month",
                    },
                },
                "quantity": 1,
            }],
            mode="subscription",
            success_url=base_success_url,
            cancel_url=base_cancel_url,
            metadata={
                "plan": plan,
                "userId": "current_user_id",  # TODO: Nutzer-ID aus Session holen
            },
        )
        return JSONResponse(content={
            "sessionId": session.id,
            "url": session.url,
            "status": "pending"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe-Fehler: {str(e)}")


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Webhook für erfolgreiche Stripe-Zahlungen.
    
    Event: checkout.session.completed
    
    Args:
        request: Stripe-Webhook-Request
    
    Returns:
        JSON mit Status
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook Secret nicht konfiguriert")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Ungültige Payload")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Ungültige Signatur")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("userId")
        plan = session.get("metadata", {}).get("plan")
        
        # TODO: Nutzer in DB aktivieren
        # db.activate_core_plan(user_id, plan)
        
        return JSONResponse(content={"status": "ok", "userId": user_id, "plan": plan})

    return JSONResponse(content={"status": "ignored", "type": event["type"]})
