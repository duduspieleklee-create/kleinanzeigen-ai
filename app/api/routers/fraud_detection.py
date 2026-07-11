"""
API-Endpunkte für die Betrugserkennung.

Endpunkte:
    - POST /api/fraud-check (manuelle Prüfung einer Anzeige)
    - GET /api/ad/{ad_id}/fraud-status (gespeicherte Prüfung einer Anzeige)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.fraud_detection import (
    analyze_ad_for_fraud,
    check_seller_for_fraud,
    check_link_for_phishing,
    check_image_for_fake,
)
from app.shared.database import get_db
from app.shared.models import FraudAlert

router = APIRouter(prefix="/api", tags=["fraud_detection"])


class AdDataPayload(BaseModel):
    title: str = ""
    description: str = ""
    price: float | None = None
    location: str = ""
    images: list[str] = []
    image_urls: list[str] = []


class SellerDataPayload(BaseModel):
    account_age_days: int = 365
    ads_count: int = 0
    total_reviews: int = 0
    negative_reviews: int = 0
    name: str = ""
    email: str = ""


@router.post("/fraud-check", summary="Manuelle Betrugsprüfung einer Anzeige")
def fraud_check(payload: AdDataPayload, db: Session = Depends(get_db)):
    """
    Prüft eine Anzeige auf Betrug und speichert das Ergebnis.

    Parameter:
        payload: Anzeigendaten (Titel, Beschreibung, Preis, Bilder)

    Rückgabe:
        dict: Ergebnis der Betrugsprüfung mit fraud_level, warnings, trust_score
    """
    try:
        ad_data = payload.model_dump()
        result = analyze_ad_for_fraud(ad_data)

        # In DB speichern für spätere Abfrage
        alert = FraudAlert(
            ad_id=0,  # wird bei Verknüpfung mit eigentlicher Anzeige gesetzt
            fraud_level=result["fraud_level"],
            warnings=result["warnings"],
            recommendation=result["recommendation"],
            trust_score=result["trust_score"],
        )
        db.add(alert)
        db.commit()
        result["alert_id"] = alert.id
        return result
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ad/{ad_id}/fraud-status", summary="Gespeicherte Betrugsprüfung einer Anzeige")
def get_fraud_status(ad_id: int, db: Session = Depends(get_db)):
    """
    Ruft die letzte Betrugsprüfung für eine Anzeige aus der DB ab.
    """
    alert = (
        db.query(FraudAlert)
        .filter(FraudAlert.ad_id == ad_id)
        .order_by(FraudAlert.created_at.desc())
        .first()
    )
    if not alert:
        return {
            "ad_id": ad_id,
            "fraud_level": "unknown",
            "warnings": [],
            "recommendation": "Keine Prüfung für diese Anzeige vorhanden.",
            "trust_score": None,
        }

    return {
        "ad_id": ad_id,
        "fraud_level": alert.fraud_level,
        "warnings": alert.warnings or [],
        "recommendation": alert.recommendation or "",
        "trust_score": alert.trust_score,
        "checked_at": alert.created_at.isoformat() if alert.created_at else None,
    }


@router.post("/fraud-check/link", summary="Link auf Phishing prüfen")
def check_link(url: str):
    """Prüft einen Link auf Phishing-Indikatoren (Issue #267)."""
    is_suspicious = check_link_for_phishing(url)
    return {
        "url": url,
        "is_suspicious": is_suspicious,
        "message": "Link ist verdächtig" if is_suspicious else "Link sieht sicher aus",
    }


@router.post("/fraud-check/image", summary="Bild auf Duplikate prüfen")
def check_image(image_url: str):
    """Prüft ob ein Bild bereits in anderen Anzeigen verwendet wurde."""
    is_known = check_image_for_fake(image_url)
    return {
        "image_url": image_url,
        "is_known": is_known,
        "message": "Bild wurde bereits in anderen Anzeigen gesehen" if is_known else "Bild scheint neu zu sein",
    }


@router.post("/fraud-check/seller", summary="Verkäufer auf Betrug prüfen")
def check_seller(payload: SellerDataPayload):
    """Prüft ein Verkäuferprofil auf verdächtige Muster."""
    result = check_seller_for_fraud(payload.model_dump())
    return result
