"""
API-Endpunkte für die Betrugserkennung.

Endpunkte:
    - POST /api/fraud-check (manuelle Prüfung einer Anzeige)
    - GET /api/ad/{id}/fraud-status (automatische Prüfung einer Anzeige)
"""

from fastapi import APIRouter, HTTPException
from app.ai.fraud_detection import analyze_ad_for_fraud

router = APIRouter(prefix="/api", tags=["fraud_detection"])


@router.post("/fraud-check", summary="Manuelle Betrugsprüfung einer Anzeige")
def fraud_check(ad_data: dict):
    """
    Prüft eine Anzeige auf Betrug.

    Parameter:
        ad_data (dict): Daten der Anzeige (z. B. {"title": "...", "description": "...", "price": 100, "images": [...]})

    Rückgabe:
        dict: Ergebnis der Betrugsprüfung
    """
    try:
        result = analyze_ad_for_fraud(ad_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ad/{ad_id}/fraud-status", summary="Automatische Betrugsprüfung einer Anzeige")
def get_fraud_status(ad_id: int):
    """
    Prüft eine Anzeige (ID) auf Betrug.

    Parameter:
        ad_id (int): ID der Anzeige

    Rückgabe:
        dict: Ergebnis der Betrugsprüfung
    """
    # TODO: Implementiere die Abfrage aus der Datenbank
    return {
        "ad_id": ad_id,
        "fraud_level": "low",
        "warnings": [],
        "recommendation": "Keine Warnungen."
    }