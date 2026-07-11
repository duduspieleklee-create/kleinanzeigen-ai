"""Tests für die erweiterten Ergebnis-Filter (app/shared/result_filters.py).

Semantik (mit Product Owner festgelegt): require = ALLE Begriffe (UND), match
über Titel + Beschreibung, GANZES Wort, case-insensitive; exclude = KEINER darf
vorkommen; exclude_locations = Teilstring gegen den Ort.
"""
from app.shared.result_filters import parse_terms, passes_filters


# ── parse_terms ─────────────────────────────────────────────────────────────

def test_parse_terms_splits_normalises_and_dedupes():
    assert parse_terms("Original, OVP\ndefekt; Original") == ["original", "ovp", "defekt"]


def test_parse_terms_keeps_multiword_terms():
    # Leerzeichen trennt NICHT — ein Term darf mehrwortig sein.
    assert parse_terms("neu ovp, sehr gut") == ["neu ovp", "sehr gut"]


def test_parse_terms_empty_and_none():
    assert parse_terms("") == []
    assert parse_terms(None) == []
    assert parse_terms("  ,  ; \n ") == []


# ── require: ALLE Begriffe (UND), ganzes Wort ───────────────────────────────

def test_require_all_terms_must_be_present():
    assert passes_filters("iPhone 13 original OVP", "top", None, require=["original", "ovp"])
    # "ovp" fehlt → durchfällt (UND-Semantik).
    assert not passes_filters("iPhone 13 original", "top", None, require=["original", "ovp"])


def test_require_matches_across_title_and_description():
    # "original" nur im Titel, "ovp" nur in der Beschreibung → beide zählen.
    assert passes_filters("iPhone original", "noch in ovp", None, require=["original", "ovp"])


def test_require_is_whole_word_not_substring():
    # "ovp" darf NICHT in "ovptasche" matchen (ganzes Wort, nicht Teilstring).
    assert not passes_filters("ovptasche", "", None, require=["ovp"])
    assert passes_filters("mit ovp dabei", "", None, require=["ovp"])


def test_matching_is_case_insensitive():
    assert passes_filters("IPHONE Original OvP", "", None, require=["original", "ovp"])


# ── exclude: KEINER darf vorkommen ──────────────────────────────────────────

def test_exclude_drops_listing_with_any_excluded_term():
    assert not passes_filters("iPhone defekt", "Displaybruch", None, exclude=["defekt", "bastler"])
    assert passes_filters("iPhone neuwertig", "top Zustand", None, exclude=["defekt", "bastler"])


def test_exclude_is_whole_word():
    # "defekt" schließt NICHT "defekte" aus (bewusst, ganzes Wort).
    assert passes_filters("defekte Verpackung, Gerät top", "", None, exclude=["defekt"])
    assert not passes_filters("Gerät defekt", "", None, exclude=["defekt"])


# ── exclude_locations: Teilstring gegen den Ort ─────────────────────────────

def test_exclude_location_by_city_or_plz():
    assert not passes_filters("Sofa", "", "66111 Saarbrücken", exclude_locations=["saarbrücken"])
    assert not passes_filters("Sofa", "", "66111 Saarbrücken", exclude_locations=["66111"])
    assert passes_filters("Sofa", "", "67655 Kaiserslautern", exclude_locations=["saarbrücken"])


def test_no_filters_always_passes():
    assert passes_filters("irgendwas", "beliebig", "Berlin")


def test_combined_filters():
    # require ok, exclude ok, location ok → bleibt.
    assert passes_filters(
        "iPhone 13 original ovp", "neuwertig", "67655 Kaiserslautern",
        require=["original"], exclude=["defekt"], exclude_locations=["saarbrücken"],
    )
    # gleiche Anzeige, aber am ausgeschlossenen Ort → fällt raus.
    assert not passes_filters(
        "iPhone 13 original ovp", "neuwertig", "66111 Saarbrücken",
        require=["original"], exclude=["defekt"], exclude_locations=["saarbrücken"],
    )
