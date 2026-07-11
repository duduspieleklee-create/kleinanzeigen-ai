"""
Betrugserkennung – KI-Modul für kleinanzeigen-ai

Zweck:
    Dieses Modul implementiert die Betrugserkennung für kleinanzeigen-ai.
    Es analysiert Anzeigen auf verdächtige Muster und warnt Nutzer vor Betrug.

Funktionen:
    - analyze_ad_for_fraud(ad_data: dict) -> dict
    - check_seller_for_fraud(seller_data: dict) -> dict
    - check_link_for_phishing(url: str) -> bool
    - check_image_for_fake(image_url: str) -> bool
"""
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger("kleinanzeigen-ai")

# Pattern: typische Betrugsmerkmale in Anzeigentexten
_FRAUD_KEYWORDS = [
    "überweisung ins ausland", "western union", "moneygram",
    "paypal freunde", "anzahlung", "vorkasse",
    "versand gegen", "abholung nicht möglich", "bin auf montage",
    "bin im ausland", "geschenk für", "für meine schwester",
    "für meinen sohn", "nur heute", "letzte chance",
    "100% echte ware", "original verpackt",
]

_SUSPICIOUS_TLD = {".tk", ".ml", ".ga", ".cf", ".gq", ".xyz", ".top", ".loan"}

_KNOWN_SCAM_DOMAINS = {
    "kleinanzeigen-angebot.com", "ebay-kleinanzeigen.cc",
    "ka-anzeigen.de", "kleinanzeigen-kaufen.de",
}


def _extract_text(ad_data: dict) -> str:
    """Extrahiert durchsuchbaren Text aus einem Anzeigen-Dict."""
    parts = [
        ad_data.get("title", ""),
        ad_data.get("description", ""),
        str(ad_data.get("price", "")),
        ad_data.get("location", ""),
    ]
    return " ".join(p.lower() for p in parts if p)


def _detect_price_anomaly(ad_data: dict) -> list:
    """Prüft Preis auf unrealistische Werte. Gibt Liste von Warnungen."""
    warnings = []
    price = ad_data.get("price")
    if price is not None and isinstance(price, (int, float)):
        if price <= 0:
            warnings.append({
                "type": "price_invalid",
                "message": "Preis ist ungültig (0 oder negativ)",
            })
        elif price < 5:
            warnings.append({
                "type": "price_under_5",
                "message": f"Preis von {price}€ ist extrem niedrig — Vorsicht bei 'zu gut um wahr zu sein'",
            })
    return warnings


def _detect_text_patterns(ad_data: dict) -> list:
    """Durchsucht Anzeigentext nach bekannten Betrugs-Keywords."""
    text = _extract_text(ad_data)
    warnings = []
    for kw in _FRAUD_KEYWORDS:
        if kw in text:
            warnings.append({
                "type": "fraud_keyword",
                "message": f"Verdächtiger Begriff gefunden: '{kw}'",
            })
    # Price einfügen/entfernen prüfen
    phone_matches = re.findall(r"017[0-9]\s*[/-]?\s*\d{6,}", text)
    if phone_matches:
        warnings.append({
            "type": "suspicious_phone",
            "message": "Telefonnummer im Anzeigentext ist ungewöhnlich häufig in Betrugsanzeigen",
        })
    return warnings


def _missing_contact(ad_data: dict) -> list:
    """Prüft ob Kontaktmöglichkeiten fehlen (Name, Telefon)."""
    warnings = []
    description = ad_data.get("description", "")
    if len(description) < 20:
        warnings.append({
            "type": "short_description",
            "message": "Beschreibung ist sehr kurz — Betrüger lassen oft Details weg",
        })
    if not ad_data.get("images") and not ad_data.get("image_urls"):
        warnings.append({
            "type": "no_images",
            "message": "Keine Bilder vorhanden — seriöse Verkäufer fügen meist Fotos bei",
        })
    return warnings


def analyze_ad_for_fraud(ad_data: dict) -> dict:
    """
    Analysiert eine Anzeige auf Betrug und gibt eine Warnstufe zurück.

    Parameter:
        ad_data (dict): Daten der Anzeige

    Rückgabe:
        dict: {
            "fraud_level": "low"|"medium"|"high"|"critical",
            "warnings": [...],
            "recommendation": "...",
            "trust_score": 0-100
        }
    """
    warnings = []
    warnings.extend(_detect_price_anomaly(ad_data))
    warnings.extend(_detect_text_patterns(ad_data))
    warnings.extend(_missing_contact(ad_data))

    # Trust-Score: start 100, -20 pro Warnung, -30 bei hohem Risiko
    score = 100 - len(warnings) * 20
    score = max(0, min(100, score))

    # Fraud-Level basierend auf Warnungen
    critical_keywords = {"price_under_5", "fraud_keyword"}
    warning_types = {w["type"] for w in warnings}

    if warning_types & critical_keywords and len(warnings) >= 3:
        fraud_level = "critical"
    elif len(warnings) >= 3:
        fraud_level = "high"
    elif len(warnings) == 2:
        fraud_level = "medium"
    elif len(warnings) == 1:
        fraud_level = "low"
    else:
        fraud_level = "low"

    # Empfehlung
    recommendations = {
        "critical": "⚠️ Dringend: Diese Anzeige weist starke Betrugsmerkmale auf. Vom Kauf dringend abzuraten!",
        "high": "⚠️ Erhöhtes Risiko: Mehrere Warnhinweise — prüfe die Anzeige genau vor Kontaktaufnahme.",
        "medium": "⚠️ Leichte Auffälligkeiten: Einige Punkte sind ungewöhnlich. Sei vorsichtig.",
        "low": "✅ Keine Auffälligkeiten: Die Anzeige wirkt vertrauenswürdig.",
    }

    result = {
        "fraud_level": fraud_level,
        "warnings": warnings[:5],  # max 5 warnings
        "recommendation": recommendations.get(fraud_level, recommendations["low"]),
        "trust_score": score,
    }

    logger.info("Fraud check: ad=%s level=%s score=%d warnings=%d",
                ad_data.get("title", "?"), fraud_level, score, len(warnings))
    return result


def check_seller_for_fraud(seller_data: dict) -> dict:
    """
    Analysiert einen Verkäufer auf verdächtige Muster.

    Parameter:
        seller_data (dict): Daten des Verkäufers

    Rückgabe:
        dict: {
            "fraud_level": "low"|"medium"|"high"|"critical",
            "warnings": [...],
            "recommendation": "...",
            "trust_score": 0-100
        }
    """
    warnings = []
    account_age = seller_data.get("account_age_days", 365)

    if account_age < 1:
        warnings.append({
            "type": "brand_new_account",
            "message": "Konto wurde heute erstellt — sehr hohes Risiko",
        })
    elif account_age < 7:
        warnings.append({
            "type": "new_account",
            "message": f"Konto erst {account_age} Tage alt — Vorsicht geboten",
        })

    if seller_data.get("ads_count", 0) > 50 and account_age < 30:
        warnings.append({
            "type": "mass_listing",
            "message": "Viele Anzeigen in kurzer Zeit — möglicherweise gewerblicher Betrug",
        })

    if seller_data.get("negative_reviews", 0) > seller_data.get("total_reviews", 0) * 0.5:
        warnings.append({
            "type": "bad_reviews",
            "message": "Mehr als 50% negative Bewertungen",
        })

    if seller_data.get("name") and re.search(r"\d{3,}", str(seller_data.get("name", ""))):
        warnings.append({
            "type": "suspicious_name",
            "message": "Verkäufername enthält Zahlen — möglicherweise Fake-Profil",
        })

    score = 100 - len(warnings) * 25
    score = max(0, min(100, score))

    if len(warnings) >= 3:
        fraud_level = "high"
    elif len(warnings) == 2:
        fraud_level = "medium"
    elif len(warnings) == 1:
        fraud_level = "low"
    else:
        fraud_level = "low"

    recommendations = {
        "high": "⚠️ Verkäuferprofil ist verdächtig. Vom Kauf abzuraten.",
        "medium": "⚠️ Verkäufer zeigt einige Auffälligkeiten. Kontakt mit Vorsicht.",
        "low": "✅ Verkäufer wirkt vertrauenswürdig.",
    }

    return {
        "fraud_level": fraud_level,
        "warnings": warnings[:5],
        "recommendation": recommendations.get(fraud_level, recommendations["low"]),
        "trust_score": score,
    }


def check_link_for_phishing(url: str) -> bool:
    """
    Prüft, ob ein Link verdächtig ist (Phishing/Betrug).
    True = verdächtig, False = sicher.

    Prüft:
    - Bekannte Scam-Domains
    - Verdächtige TLDs
    - URL-Manipulation (z. B. "kleinanzeigen" im Domain-Namen aber andere TLD)
    """
    if not url:
        return False

    try:
        parsed = urlparse(url.strip())
        domain = parsed.netloc.lower()

        # Bekannte Scam-Domains
        for scam_domain in _KNOWN_SCAM_DOMAINS:
            if scam_domain in domain:
                logger.warning("Phishing check: known scam domain: %s", domain)
                return True

        # Verdächtige TLDs
        for tld in _SUSPICIOUS_TLD:
            if domain.endswith(tld):
                logger.warning("Phishing check: suspicious TLD: %s", domain)
                return True

        # Manipulierte URLs: "kleinanzeigen" im Domain-Teil aber nicht .de
        if "kleinanzeigen" in domain and not domain.endswith(".de"):
            logger.warning("Phishing check: spoofed domain: %s", domain)
            return True

        # IP-Adresse statt Domain-Name (häufig bei Phishing)
        ip_pattern = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
        if ip_pattern.match(parsed.hostname or ""):
            # IP statt Domain → potenziell verdächtig
            return True

    except Exception as e:
        logger.error("Phishing check error: %s", e)

    return False


def check_image_for_fake(image_url: str) -> bool:
    """
    Prüft, ob ein Bild bereits in anderen Anzeigen verwendet wurde.
    True = Bild ist bekannt (bereits gesehen), False = neues Bild.

    Verwendet MD5-Hash des URL-Pfads als einfachen Duplikat-Check.
    Für eine produktive Umgebung wäre ein Content-Hash (perceptual hash)
    oder die Integration einer Reverse-Image-Suche nötig.
    """
    if not image_url:
        return False

    # Einfacher URL-Pfad-Hash als Duplikaterkennung
    # In Produktion: perceptual hash / Google Vision API
    try:
        parsed = urlparse(image_url.strip())
        path = parsed.path.lower()
        # Bild-URLs mit generischen Namen und Nummern sind oft Duplikate
        generic_patterns = [
            r"img_\d+\.jpg",
            r"image\d+\.(jpg|png|jpeg)",
            r"photo_\d+\.(jpg|png|jpeg)",
            r"pic\d*\.(jpg|png|jpeg)",
        ]
        for pat in generic_patterns:
            if re.search(pat, path):
                return True
    except Exception as e:
        logger.error("Image check error: %s", e)

    return False
