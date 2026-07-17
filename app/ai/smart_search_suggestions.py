"""
Smart Search Suggestions – KI-Modul für kleinanzeigen-ai
Zweck: Generiert Suchvorschläge basierend auf Nutzeranfragen.

API-Integration:
- Datamuse (kostenlos, Englisch/Deutsch) für Synonyme
- Wikipedia (kostenlos, Deutsch) für verwandte Begriffe
- Lokale Trends-Datenbank (data/trends.json) für aktuelle Trends
- Optional: Custom Model Endpoint (OpenAI-kompatibel) für KI-Vorschläge
- Fallback zu Mock-Daten bei API-Fehlern
"""

from typing import List, Dict
import requests
import logging
import json
import re
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential

from app.api.config import settings
from app.shared.proxy import is_safe_proxy_url

logger = logging.getLogger("kleinanzeigen-ai")


class SmartSearchSuggestions:
    """KI-Modul für intelligente Suchvorschläge."""

    def __init__(self):
        # Mock-Daten für Fallback
        self.synonyms = {
            "Auto": ["PKW", "Wagen", "Fahrzeug", "Pkw", "Kfz"],
            "Haus": ["Wohnung", "Immobilie", "Gebäude", "Bungalow"],
            "Handy": ["Smartphone", "Mobiltelefon", "Handy"],
            "Garten": ["Außenbereich", "Terrasse", "Balkon"],
            "Schuhe": ["Sneaker", "Stiefel", "Sandalen"],
        }
        self.related_terms = {
            "Auto": ["Reifen", "Motor", "Fahrer", "Bremse", "Getriebe"],
            "Haus": ["Dach", "Fenster", "Tür", "Keller", "Garten"],
            "Handy": ["Akku", "Display", "Kamera", "Ladegerät"],
            "Garten": ["Pflanze", "Blume", "Rasen", "Gartengeräte"],
            "Schuhe": ["Sohle", "Schnürsenkel", "Einlagen"],
        }
        self.cache = {}  # Cache für Suchvorschläge (Struktur: {"query": {"data": ..., "timestamp": datetime}})
        self.trends = self._load_trends()

    def _load_trends(self) -> Dict[str, List[str]]:
        """Lädt Trends aus der lokalen Datenbank."""
        try:
            trends_path = Path(__file__).parent.parent / ".." / "data" / "trends.json"
            with open(trends_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Fehler beim Laden der Trends-Datenbank: {e}")
            return {}

    def get_local_trends(self, keyword: str) -> List[str]:
        """Holt Trends aus der lokalen Datenbank."""
        return self.trends.get(keyword, [])

    def get_synonyms(self, keyword: str) -> List[str]:
        """Holt Synonyme von Datamuse-API (Fallback zu Mock-Daten)."""
        try:
            return self._fetch_synonyms_from_datamuse(keyword)
        except Exception as e:
            logger.warning("Datamuse-API-Fehler (Fallback genutzt): %s", e)
            return self.synonyms.get(keyword, [])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=0.1, max=0.5),
        reraise=True,
    )
    def _fetch_synonyms_from_datamuse(self, keyword: str) -> List[str]:
        response = requests.get(
            "https://api.datamuse.com/words",
            params={"rel_syn": keyword, "max": 10},
            timeout=5,
        )
        response.raise_for_status()
        return [item["word"] for item in response.json()]

    def get_related_terms(self, keyword: str) -> List[str]:
        """Holt verwandte Begriffe von Wikipedia-API (Fallback zu Mock-Daten)."""
        try:
            return self._fetch_related_terms_from_wikipedia(keyword)
        except Exception as e:
            logger.warning("Wikipedia-API-Fehler (Fallback genutzt): %s", e)
            return self.related_terms.get(keyword, [])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=0.1, max=0.5),
        reraise=True,
    )
    def _fetch_related_terms_from_wikipedia(self, keyword: str) -> List[str]:
        response = requests.get(
            "https://de.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": keyword,
                "format": "json",
            },
            headers={"User-Agent": "kleinanzeigen-ai/1.0"},
            timeout=5,
        )
        response.raise_for_status()
        titles = [
            item["title"]
            for item in response.json().get("query", {}).get("search", [])
        ]
        return [title.split("–")[0].strip() for title in titles]

    def get_custom_model_suggestions(self, query: str) -> List[str]:
        """Fragt einen OpenAI-kompatiblen Custom-Model-Endpoint nach Vorschlägen.

        Erfordert settings.custom_model_endpoint und settings.custom_model_name.
        Bei Fehlern oder fehlender Konfiguration → leere Liste (kein Abbruch).
        """
        if not (settings.custom_model_endpoint_resolved and settings.custom_model_name):
            return []

        url = settings.custom_model_endpoint_resolved.rstrip("/") + "/chat/completions"
        safe, reason = is_safe_proxy_url(url)
        if not safe:
            logger.warning("Refusing custom model request to unsafe endpoint: %s (%s)", url, reason)
            return []

        headers = {"Content-Type": "application/json"}
        if settings.custom_model_api_key_resolved:
            headers["Authorization"] = f"Bearer {settings.custom_model_api_key_resolved}"

        payload = {
            "model": settings.custom_model_name,
            "temperature": settings.custom_model_temperature,
            "max_tokens": settings.custom_model_max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Du bist ein Such-Assistent für die Plattform kleinanzeigen.de. "
                        "Gib ausschließlich reale Suchbegriffe zurück, wie sie Nutzer "
                        "dort eingeben würden – auch Synonyme und verwandte Begriffe "
                        "zum Suchbegriff. "
                        "Regeln: GENAU ein Suchbegriff pro Zeile. KEINE Nummerierung "
                        "(kein '1.', '2.' oder '1)'), KEINE Aufzählungszeichen, "
                        "KEIN erklärender Text, KEINE Einleitung, KEINE Anführungszeichen. "
                        "Nur konkrete, verkaufsrelevante Begriffe (z.B. 'Gebrauchtwagen', "
                        "'PKW kaufen', 'Auto gebraucht'). Liefere mindestens 5 Begriffe. "
                        "Beispielausgabe:\n"
                        "Gebrauchtwagen\n"
                        "PKW kaufen\n"
                        "Auto gebraucht"
                    ),
                },
                {
                    "role": "user",
                    "content": f"Schlage passende Suchbegriffe für: {query}",
                },
            ],
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            raw = re.split(r"[\n\r]+", content)
            suggestions = []
            for line in raw:
                # Entferne umschließende Satzzeichen/Symbole (kein Backslash-Escaping)
                line = line.strip().strip("\"'`*•–—- ")
                # Entferne führende Nummerierung wie "1." "2)" "3 -"
                line = re.sub(r"^\s*\d+[.)•-]?\s*", "", line).strip()
                line = line.strip("\"'`*•–—- ")
                # Mindestens 2 Zeichen, maximal 60 (keine reinen Satzzeichen)
                if line and 1 < len(line) <= 60:
                    suggestions.append(line)
            # Dedupe (case-insensitive), Reihenfolge bewahren
            seen = set()
            unique = []
            for s in suggestions:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    unique.append(s)
            return unique[:10]
        except Exception as e:
            logger.error(f"Custom-Model-Endpoint-Fehler: {e}")
            return []

    def get_suggestions(self, query: str) -> Dict[str, List[str]]:
        """Generiert Suchvorschläge für eine Nutzeranfrage."""
        from datetime import datetime, timedelta
        
        # Cache-Invalidierung (TTL: 1 Stunde)
        if query in self.cache:
            cached_data = self.cache[query]
            if datetime.now() - cached_data["timestamp"] < timedelta(hours=1):
                return cached_data["data"]
            else:
                del self.cache[query]

        keywords = query.split()
        suggestions: Dict[str, List[str]] = {}

        for keyword in keywords:
            synonyms = self.get_synonyms(keyword)
            related_terms = self.get_related_terms(keyword)
            local_trends = self.get_local_trends(keyword)

            if synonyms:
                suggestions[f"Synonyme für '{keyword}'"] = synonyms
            if related_terms:
                suggestions[f"Verwandte Begriffe für '{keyword}'"] = related_terms
            if local_trends:
                suggestions[f"Aktuelle Trends für '{keyword}'"] = local_trends

        # Google Trends — immer aktiv, Fallback bei Fehlern
        try:
            from app.ai.smart_search_trends import get_trending_searches_batch
            trends = get_trending_searches_batch(keywords)
            for keyword, items in trends.items():
                if items:
                    suggestions[f"Google Trends zu '{keyword}'"] = items
        except Exception:
            pass

        if settings.custom_model_enabled:
            custom = self.get_custom_model_suggestions(query)
            if custom:
                suggestions["KI-Vorschläge (Custom Model)"] = custom

        self.cache[query] = {"data": suggestions, "timestamp": datetime.now()}
        return suggestions


# Instanz des Moduls
smart_search = SmartSearchSuggestions()
