"""Tests für build_push_notification (app/shared/smart_alerts.py).

Deckt die neue, wertorientierte Push-Notification ab:
- Deal-Variante (konkrete Suche + Angebot unter Marktpreis): Ersparnis in €,
  Preis, Ort, Trust-Score im Text.
- Fallback ohne Deal: Anzahl + günstigster Preis + Ort, alles auf Deutsch.
- Kein "unter Marktpreis" ohne Keywords (Kategorie-/Service-Stöbern).
- Kategorie-Profile (Jobs/Immobilien/Dienstleistungen/Verschenken/Tiere/
  Gesuche, siehe app/shared/category_profiles.py): kein Preisvergleich,
  stattdessen passende Formulierung + Dringlichkeit + Trust-Score nur wo
  sinnvoll UND vom Caller freigegeben (Core/Pro-Gate liegt beim Aufrufer,
  nicht in build_push_notification — siehe die *_profile_* Tests unten).
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


# ── Kategorie-Profile: kein Preisvergleich, andere Formulierung/Prioritäten ──

def test_job_profile_never_frames_as_deal():
    n = build_push_notification(
        new_count=3, keywords="Lagerhelfer", location="Berlin", profile="job",
    )
    assert n["title"] == "🧑‍💼 3 neue Stellenangebote für „Lagerhelfer“"
    assert "unter Marktpreis" not in n["title"] and "unter Marktpreis" not in n["body"]
    assert "📍 Berlin" in n["body"]
    assert "Jetzt ansehen, bevor sie weg sind" in n["body"]


def test_job_profile_never_shows_trust_even_if_passed():
    # Jobs have no meaningful "seller trust" concept — the profile must
    # ignore a trust_score even if a caller passes one by mistake.
    n = build_push_notification(
        new_count=1, keywords="", location="Hamburg", profile="job",
        trust_score=95, sample_title="Lagerhelfer (m/w/d)",
    )
    assert "⭐" not in n["body"]
    assert "Lagerhelfer (m/w/d)" in n["body"]


def test_real_estate_profile_shows_price_without_deal_framing():
    n = build_push_notification(
        new_count=1, keywords="3-Zimmer", cheapest_price="950 €", location="München",
        profile="real_estate", sample_title="3-Zimmer Altbau Sendling",
    )
    assert "unter Marktpreis" not in n["title"] and "%" not in n["body"]
    assert "3-Zimmer Altbau Sendling" in n["body"]
    assert "950 €" in n["body"] and "ab 950 €" not in n["body"]  # single hit: no "ab" prefix
    assert "Wohnungen gehen oft in Minuten weg" in n["body"]


def test_real_estate_profile_multiple_hits_uses_ab_prefix():
    n = build_push_notification(
        new_count=4, cheapest_price="800 €", location="Köln", profile="real_estate",
    )
    assert n["title"] == "🏠 4 neue Immobilien"
    assert "ab 800 €" in n["body"]


def test_service_profile_shows_trust_when_caller_allows_it():
    n = build_push_notification(
        new_count=2, keywords="Umzugshelfer", location="Umkreis 20 km",
        profile="service", trust_score=88,
    )
    assert "⭐ Anbieter 88/100" in n["body"]
    assert "unter Marktpreis" not in n["title"]


def test_service_profile_hides_trust_when_caller_gates_it_out():
    # Basic plan: caller passes trust_score=None (see app/worker/tasks.py's
    # show_trust gate) — the notification must degrade gracefully, not error.
    n = build_push_notification(
        new_count=2, keywords="Umzugshelfer", location="Umkreis 20 km",
        profile="service", trust_score=None,
    )
    assert "⭐" not in n["body"]
    assert "📍 Umkreis 20 km" in n["body"]


def test_giveaway_profile_has_urgency_not_savings():
    n = build_push_notification(
        new_count=1, location="Berlin", profile="giveaway", sample_title="Sofa, gut erhalten",
    )
    assert "€" not in n["body"]  # no price/savings framing for free items
    assert "Kostenlose Sachen sind sehr schnell weg" in n["body"]
    assert "Sofa, gut erhalten" in n["body"]


def test_animal_profile_trust_score_gated_like_service():
    with_trust = build_push_notification(
        new_count=1, keywords="Golden Retriever Welpen", location="Umkreis 50 km",
        profile="animal", trust_score=76, sample_title="Golden Retriever Welpen, 8 Wochen",
    )
    without_trust = build_push_notification(
        new_count=1, keywords="Golden Retriever Welpen", location="Umkreis 50 km",
        profile="animal", trust_score=None, sample_title="Golden Retriever Welpen, 8 Wochen",
    )
    assert "⭐ Anbieter 76/100" in with_trust["body"]
    assert "⭐" not in without_trust["body"]
    assert "unter Marktpreis" not in with_trust["title"]


def test_gesuche_profile_has_no_price_concept():
    n = build_push_notification(
        new_count=4, keywords="Klavier", location="Umkreis 30 km", profile="gesuche",
    )
    assert n["title"] == "🔎 4 neue Gesuche für „Klavier“"
    assert "€" not in n["body"]


def test_unknown_profile_falls_back_to_item_logic():
    # A category not in _PROFILE_COPY (e.g. "vehicle", "ticket", or the
    # default "item") must fall through to the existing deal/fallback logic
    # unchanged — this is the whole point of keeping those out of the map.
    n = build_push_notification(
        new_count=2, keywords="BMW 320d", cheapest_price="14.800 €",
        location="Hamburg", profile="vehicle",
    )
    assert "ab 14.800 €" in n["body"]
    assert "📍 Hamburg" in n["body"]
