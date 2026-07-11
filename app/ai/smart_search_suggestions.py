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

from app.api.config import settings

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
        self.cache = {}  # Cache für Suchvorschläge
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
            response = requests.get(
                "https://api.datamuse.com/words",
                params={"rel_syn": keyword, "max": 10},
                timeout=5,
            )
            response.raise_for_status()
            return [item["word"] for item in response.json()]
        except Exception as e:
            logger.error(f"Datamuse-API-Fehler: {e}")
            return self.synonyms.get(keyword, [])

    def get_related_terms(self, keyword: str) -> List[str]:
        """Holt verwandte Begriffe von Wikipedia-API (Fallback zu Mock-Daten)."""
        try:
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
        except Exception as e:
            logger.error(f"Wikipedia-API-Fehler: {e}")
            return self.related_terms.get(keyword, [])

    def get_custom_model_suggestions(self, query: str) -> List[str]:
        """Fragt einen OpenAI-kompatiblen Custom-Model-Endpoint nach Vorschlägen.

        Erfordert settings.custom_model_endpoint und settings.custom_model_name.
        Bei Fehlern oder fehlender Konfiguration → leere Liste (kein Abbruch).
        """
        if not (settings.custom_model_endpoint and settings.custom_model_name):
            return []

        url = settings.custom_model_endpoint.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if settings.custom_model_api_key:
            headers["Authorization"] = f"Bearer {settings.custom_model_api_key}"

        payload = {
            "model": settings.custom_model_name,
            "temperature": settings.custom_model_temperature,
            "max_tokens": settings.custom_model_max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Du bist ein Such-Assistent für eine Kleinanzeigen-Plattform. "
                        "Gib ausschließlich relevante Suchbegriffe zurück. "
                        "Regeln: GENAU ein Suchbegriff pro Zeile. KEINE Nummerierung "
                        "(kein '1.', '2.' oder '1)'), KEINE Aufzählungszeichen, "
                        "KEIN erklärender Text, KEINE Einleitung. "
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
                line = line.strip()
                # Entferne führende Nummerierung wie "1." "2)" "3 -" und Symbole
                line = re.sub(r"^\s*\d+[\.\)\-\•\*\u2022]?\s*", "", line).strip(" -\u2022\u2023")
                line = line.strip()
                if line:
                    suggestions.append(line)
            return suggestions[:10]
        except Exception as e:
            logger.error(f"Custom-Model-Endpoint-Fehler: {e}")
            return []

    def get_suggestions(self, query: str) -> Dict[str, List[str]]:
        """Generiert Suchvorschläge für eine Nutzeranfrage."""
        if query in self.cache:
            return self.cache[query]

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

        if settings.custom_model_enabled:
            custom = self.get_custom_model_suggestions(query)
            if custom:
                suggestions["KI-Vorschläge (Custom Model)"] = custom

        self.cache[query] = suggestions
        return suggestions


# Instanz des Moduls
smart_search = SmartSearchSuggestions()
