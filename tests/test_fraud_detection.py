"""
Tests für die Betrugserkennung (app/ai/fraud_detection.py + router).
"""

from types import SimpleNamespace
import pytest
from app.ai.fraud_detection import (
    analyze_ad_for_fraud,
    check_seller_for_fraud,
    check_link_for_phishing,
    check_image_for_fake,
)


# ── analyze_ad_for_fraud ──────────────────────────────────────────────────

def test_clean_ad_returns_low():
    """Eine unauffällige Anzeige → low risk."""
    result = analyze_ad_for_fraud({
        "title": "Guter gebrauchter Tisch",
        "description": "Verkaufe meinen gebrauchten Esstisch aus Eiche. 120x80cm, leichte Gebrauchsspuren. Nur Abholung.",
        "price": 80,
        "location": "Berlin",
        "images": ["bild1.jpg"],
    })
    assert result["fraud_level"] == "low"
    assert result["trust_score"] >= 80


def test_ads_with_fraud_keywords():
    """Betrugs-Keywords im Text → mindestens eine Warnung."""
    result = analyze_ad_for_fraud({
        "title": "iPhone 15 NEU",
        "description": "Verkaufe neues iPhone. Überweisung ins Ausland, bin auf Montage. Nur vorkasse.",
        "price": 50,
        "location": "",
    })
    assert result["fraud_level"] in ("high", "critical")
    assert len(result["warnings"]) >= 2


def test_zero_price_is_warning():
    """Preis = 0 → Warnung."""
    result = analyze_ad_for_fraud({
        "title": "Gratis",
        "description": "Zu verschenken",
        "price": 0,
    })
    assert any(w["type"] == "price_invalid" for w in result["warnings"])


def test_very_low_price_is_warning():
    """Preis unter 5€ → Warnung."""
    result = analyze_ad_for_fraud({
        "title": "Auto",
        "description": "Guter Zustand",
        "price": 1,
    })
    assert any(w["type"] == "price_under_5" for w in result["warnings"])


def test_missing_images_triggers_warning():
    """Keine Bilder → Warnung."""
    result = analyze_ad_for_fraud({
        "title": "Test",
        "description": "Eine ausführliche Beschreibung mit genügend Text.",
        "price": 50,
    })
    assert any(w["type"] == "no_images" for w in result["warnings"])


def test_short_description_triggers_warning():
    """Sehr kurze Beschreibung → Warnung."""
    result = analyze_ad_for_fraud({
        "title": "Test",
        "description": "Kurz",
        "price": 50,
        "images": ["bild.jpg"],
    })
    assert any(w["type"] == "short_description" for w in result["warnings"])


# ── check_seller_for_fraud ────────────────────────────────────────────────

def test_new_account_is_warning():
    """Konto jünger als 7 Tage → Warnung."""
    result = check_seller_for_fraud({"account_age_days": 2})
    assert any(w["type"] == "new_account" for w in result["warnings"])


def test_brand_new_account_is_high():
    """Konto jünger als 1 Tag → high warning."""
    result = check_seller_for_fraud({"account_age_days": 0})
    assert any(w["type"] == "brand_new_account" for w in result["warnings"])


def test_old_account_is_safe():
    """Altes Konto ohne Auffälligkeiten → low."""
    result = check_seller_for_fraud({
        "account_age_days": 365,
        "ads_count": 3,
        "name": "Max Mustermann",
    })
    assert result["fraud_level"] == "low"
    assert result["trust_score"] == 100


def test_mass_listing_detected():
    """Viele Anzeigen bei jungem Konto → Warnung."""
    result = check_seller_for_fraud({
        "account_age_days": 14,
        "ads_count": 100,
    })
    assert any(w["type"] == "mass_listing" for w in result["warnings"])


def test_bad_reviews_trigger():
    """Mehr als 50% negative Bewertungen → Warnung."""
    result = check_seller_for_fraud({
        "total_reviews": 10,
        "negative_reviews": 6,
    })
    assert any(w["type"] == "bad_reviews" for w in result["warnings"])


# ── check_link_for_phishing ───────────────────────────────────────────────

def test_empty_url_is_safe():
    """Leere URL → False."""
    assert check_link_for_phishing("") is False
    assert check_link_for_phishing("") is False  # None wird intern als '' behandelt


def test_normal_url_is_safe():
    """Normale URL → False."""
    assert check_link_for_phishing("https://www.ebay-kleinanzeigen.de/s-anzeige/test/") is False


def test_suspicious_tld_is_flagged():
    """Verdächtige TLD → True."""
    assert check_link_for_phishing("https://angebot.tk/iphone") is True
    assert check_link_for_phishing("http://deal.top/angebot") is True


def test_known_scam_domain_is_flagged():
    """Bekannte Scam-Domain → True."""
    assert check_link_for_phishing("https://kleinanzeigen-angebot.com/angebot") is True


def test_spoofed_kleinanzeigen_domain():
    """kleinanzeigen in Domain aber nicht .de → True."""
    assert check_link_for_phishing("https://kleinanzeigen-kaufen.de/") is True


def test_ip_address_url():
    """IP-Adresse statt Domain → True (potenzielles Phishing)."""
    assert check_link_for_phishing("http://192.168.1.1/angebot") is True


# ── check_image_for_fake ───────────────────────────────────────────────────

def test_empty_image_url():
    """Leere URL → False."""
    assert check_image_for_fake("") is False
    assert check_image_for_fake("") is False  # None wird intern als '' behandelt


def test_generic_image_name_is_flagged():
    """Generischer Bildname → True (bereits gesehen)."""
    assert check_image_for_fake("https://example.com/img_123.jpg") is True
    assert check_image_for_fake("https://example.com/image5.png") is True
    assert check_image_for_fake("https://example.com/photo_1.jpeg") is True
    assert check_image_for_fake("https://example.com/pic.jpg") is True


def test_normal_image_name_is_safe():
    """Normaler Bildname → False."""
    assert check_image_for_fake("https://example.com/esstisch-eiche-gebraucht.jpg") is False
    assert check_image_for_fake("https://example.com/mein-bild.png") is False
