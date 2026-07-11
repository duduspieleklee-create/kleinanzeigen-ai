"""Tests für das Kategorie-Code-Mapping (app/shared/category_codes.py) und
dessen Einbau in build_kleinanzeigen_url.

Kernpunkt: kleinanzeigen filtert eine Kategorie über den ``c{id}``-Code im
k-Token, NICHT über das ``s-{slug}``-Pfadsegment. Ohne c-Code degradiert die
Suche zu einer Volltextsuche über alle Kategorien (der Bug, den dieses Modul
behebt). Der wichtigste Test hier (``test_every_dashboard_category_is_mapped``)
liest die Slugs direkt aus dashboard.html, damit eine später hinzugefügte
Kategorie ohne Code sofort auffällt.
"""
import re
from pathlib import Path

from app.shared.category_codes import CATEGORY_CODES, category_code
from app.shared.url_builder import build_kleinanzeigen_url

_DASHBOARD = Path("app/api/templates/dashboard.html")


def _dashboard_category_slugs() -> set[str]:
    """Alle <option value>-Slugs aus dem category_options-Makro in dashboard.html."""
    html = _DASHBOARD.read_text(encoding="utf-8")
    macro = re.search(
        r"macro category_options.*?endmacro", html, re.DOTALL
    )
    assert macro, "category_options-Makro nicht in dashboard.html gefunden"
    slugs = set(re.findall(r'<option value="([a-z0-9-]+)"', macro.group(0)))
    slugs.discard("")  # "Alle Kategorien" hat value=""
    return slugs


def test_every_dashboard_category_is_mapped():
    # Jede im Dashboard wählbare Kategorie MUSS einen kleinanzeigen-Code haben,
    # sonst filtert die Suche nicht (Volltext-Fallback über alle Kategorien).
    missing = sorted(s for s in _dashboard_category_slugs() if category_code(s) is None)
    assert missing == [], f"Kategorien ohne kleinanzeigen-Code: {missing}"


def test_no_stale_codes_without_dashboard_option():
    # Umgekehrt: kein Code für einen Slug, den das Dashboard gar nicht anbietet
    # (fängt Tippfehler / umbenannte Slugs, die sonst still nie greifen würden).
    slugs = _dashboard_category_slugs()
    stale = sorted(k for k in CATEGORY_CODES if k not in slugs)
    assert stale == [], f"Codes ohne passende Dashboard-Option: {stale}"


def test_codes_are_positive_ints_and_unique():
    assert all(isinstance(v, int) and v > 0 for v in CATEGORY_CODES.values())
    # Keine zwei Slugs auf dieselbe ID — jede Dashboard-Kategorie ist distinkt.
    assert len(set(CATEGORY_CODES.values())) == len(CATEGORY_CODES)


def test_category_code_returns_none_for_unmapped_or_empty():
    assert category_code(None) is None
    assert category_code("") is None
    assert category_code("gibt-es-nicht") is None


def test_url_embeds_category_code_in_k_token():
    url = build_kleinanzeigen_url(category="haus-kaufen")
    assert url.endswith("/k0c208"), url
    assert "unter" not in url  # sanity


def test_url_orders_codes_category_location_radius():
    # Reihenfolge im k-Token muss c{cat} l{loc} r{radius} sein (k0c…l…r…).
    url = build_kleinanzeigen_url(
        category="haus-kaufen", location="Berlin", location_id=3331, radius=20
    )
    assert "/k0c208l3331r20" in url, url


def test_keyword_only_search_has_no_category_code():
    # Ohne Kategorie bleibt das Verhalten unverändert: nacktes k0, kein c-Code.
    url = build_kleinanzeigen_url(keywords="iphone")
    assert url.endswith("/k0"), url
    assert "c" not in url.rsplit("/", 1)[1]  # kein c… im letzten Segment


def test_unmapped_category_falls_back_to_no_code():
    # Unbekannte Kategorie darf NICHT geraten werden — lieber kein Filter als
    # der falsche. k-Token bleibt nacktes k0.
    url = build_kleinanzeigen_url(category="unbekannte-kategorie")
    assert url.endswith("/k0"), url


def test_disambiguated_slugs_use_dashboard_branch():
    # Slugs, die in kleinanzeigens Baum mehrfach vorkommen, müssen den Zweig
    # treffen, unter dem das Dashboard sie einsortiert — nicht den anderen.
    assert category_code("umzug-transport") == 296     # Dienstleistungen, nicht 238 (Immobilien)
    assert category_code("beauty-gesundheit") == 224   # Mode & Beauty, nicht 269 (Unterricht)
    assert category_code("altenpflege") == 236         # Familie, nicht 288 (Dienstleistungen)
    assert category_code("multimedia-elektronik") == 161  # Elektronik-Root, nicht 293
    assert category_code("tierbetreuung-training") == 133  # Tiere, nicht 295 (Dienstleistungen)
