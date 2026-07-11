"""Tests für build_push_notification (app/shared/smart_alerts.py).

Deckt die neue, wertorientierte Push-Notification ab:
- Deal-Variante (konkrete Suche + Angebot unter Marktpreis): Ersparnis in €,
  Preis, Ort, Trust-Score im Text.
- Fallback ohne Deal: Anzahl + günstigster Preis + Ort, alles auf Deutsch.
- Kein "unter Marktpreis" ohne Keywords (Kategorie-/Service-Stöbern).
"""
from app.shared.smart_alerts import build_push_notification


def test_deal_shows_saving_price_location_and_trust():
    n = build_push_notification(
        new_count=3,
        keywords="iPhone 13",
        location="München",
        deal={"title": "iPhone 13 128GB", "price": "380 €",
              "saving_eur": 42, "trust_score": 92},
    )
    assert n["title"] == "🔥 42 € unter Marktpreis"
    assert "iPhone 13 128GB – 380 €" in n["body"]
    assert "📍 München" in n["body"]
    assert "⭐ Verkäufer 92/100" in n["body"]


def test_deal_without_saving_falls_back_to_generic_deal_title():
    n = build_push_notification(
        new_count=1, keywords="PS5",
        deal={"title": "PS5 Slim", "price": "240 €", "saving_eur": None, "trust_score": None},
    )
    assert n["title"] == "🔥 Top-Deal gefunden"
    assert "PS5 Slim – 240 €" in n["body"]


def test_free_item_price_is_geschenkt():
    n = build_push_notification(
        new_count=1, keywords="Sofa", location="Berlin",
        deal={"title": "Couch", "price": "geschenkt", "saving_eur": 150, "trust_score": None},
    )
    assert "Couch – geschenkt" in n["body"]
    assert "150 € unter Marktpreis" in n["title"]


def test_fallback_with_keywords_shows_count_cheapest_and_location():
    n = build_push_notification(
        new_count=3, keywords="Fahrrad", cheapest_price="120 €", location="Hamburg",
    )
    assert n["title"] == "🆕 3 neue Treffer für „Fahrrad“"
    assert "ab 120 €" in n["body"]
    assert "📍 Hamburg" in n["body"]


def test_singular_count():
    n = build_push_notification(new_count=1, keywords="Tisch", cheapest_price="50 €")
    assert n["title"] == "🆕 1 neuer Treffer für „Tisch“"


def test_no_keywords_omits_subject_and_never_says_below_market():
    # Kategorie-/Service-Stöbern: kein Keyword -> kein "unter Marktpreis",
    # kein „…"-Subjekt, aber trotzdem nützlich (Anzahl + Ort).
    n = build_push_notification(new_count=5, keywords="", location="Köln")
    assert n["title"] == "🆕 5 neue Treffer"
    assert "unter Marktpreis" not in n["title"]
    assert "📍 Köln" in n["body"]


def test_fallback_without_any_meta_has_sensible_body():
    n = build_push_notification(new_count=2, keywords="Auto")
    assert n["body"] == "Jetzt ansehen"
