"""Tests für resolve_profile (app/shared/category_profiles.py).

Deckt ab: die Kategorie-Slug-Zuordnung selbst, den ad_type="gesuche"-Override
(gewinnt immer gegen die Kategorie), sowie den Fallback auf "item" für
unbekannte/fehlende Kategorien (das erhält absichtlich das bestehende
Preisvergleichs-Verhalten für alles, was nicht explizit gemappt ist).
"""
from app.shared.category_profiles import (
    CATEGORY_PROFILES,
    NO_PRICE_PROFILES,
    resolve_profile,
)


def test_job_categories_resolve_to_job_profile():
    for slug in (
        "jobs", "ausbildung", "praktika", "heimarbeit-mini-nebenjobs",
        "bueroarbeit-verwaltung", "gastronomie-tourismus",
        "bau-handwerk-produktion", "vertrieb-einkauf-verkauf",
    ):
        assert resolve_profile(slug) == "job"


def test_real_estate_categories_resolve_to_real_estate_profile():
    for slug in (
        "wohnung-mieten", "wohnung-kaufen", "haus-mieten", "haus-kaufen",
        "auf-zeit-wg", "garage-lagerraum", "grundstuecke-garten",
        "gewerbeimmobilien", "ferienwohnung-ferienhaus",
    ):
        assert resolve_profile(slug) == "real_estate"


def test_service_categories_resolve_to_service_profile():
    for slug in (
        "dienstleistungen", "umzug-transport", "unterricht-kurse",
        "nachhilfe", "sprachkurse", "nachbarschaftshilfe",
    ):
        assert resolve_profile(slug) == "service"


def test_giveaway_categories_resolve_to_giveaway_profile():
    assert resolve_profile("zu-verschenken") == "giveaway"
    assert resolve_profile("zu-verschenken-tauschen") == "giveaway"


def test_animal_categories_resolve_to_animal_profile():
    for slug in (
        "hunde", "katzen", "kleintiere", "voegel", "fische", "pferde",
        "nutztiere", "tierbetreuung-training", "zubehoer",
    ):
        assert resolve_profile(slug) == "animal"


def test_unmapped_category_falls_back_to_item():
    # Generic item categories (Elektronik, Mode, Autos, Tickets, ...) are
    # deliberately NOT in CATEGORY_PROFILES — "item" is the existing
    # price-comparison behaviour and stays the default for anything not
    # explicitly mapped, including categories added to the wizard later.
    assert resolve_profile("multimedia-elektronik") == "item"
    assert resolve_profile("autos") == "item"
    assert resolve_profile("konzerte") == "item"
    assert resolve_profile("some-future-category-not-yet-mapped") == "item"


def test_no_category_falls_back_to_item():
    assert resolve_profile(None) == "item"
    assert resolve_profile("") == "item"


def test_gesuche_ad_type_always_wins_over_category():
    # "gesuche" means the user watches for demand (someone looking for
    # something), not supply — no "market price" concept applies regardless
    # of which category the want-ad happens to be filed under.
    assert resolve_profile("autos", "gesuche") == "gesuche"
    assert resolve_profile("hunde", "gesuche") == "gesuche"
    assert resolve_profile(None, "gesuche") == "gesuche"


def test_angebote_ad_type_does_not_override_category():
    assert resolve_profile("hunde", "angebote") == "animal"
    assert resolve_profile(None, "angebote") == "item"


def test_no_price_profiles_matches_documented_set():
    assert NO_PRICE_PROFILES == {
        "job", "real_estate", "service", "giveaway", "animal", "gesuche",
    }


def test_category_profiles_only_maps_to_no_price_profiles():
    # Every value CATEGORY_PROFILES can produce must be a NO_PRICE_PROFILES
    # entry — the dashboard's generic item/vehicle/ticket categories are
    # intentionally absent from the map so they keep the "item" default.
    assert set(CATEGORY_PROFILES.values()) <= NO_PRICE_PROFILES
