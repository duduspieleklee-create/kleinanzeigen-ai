"""
Smart Search Suggestions – KI-Modul für kleinanzeigen-ai
Zweck: Generiert Suchvorschläge basierend auf Nutzeranfragen.

API-Integration:
- Datamuse (kostenlos, Englisch/Deutsch)
- Wikipedia (kostenlos, Deutsch)
- Fallback zu Mock-Daten bei API-Fehlern
"""

from typing import List, Dict
import requests
import logging
from pytrends.request import TrendReq

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

    def get_synonyms(self, keyword: str) -> List[str]:
        """Holt Synonyme von Datamuse-API."""
        try:
            response = requests.get(
                "https://api.datamuse.com/words",
                params={"rel_syn": keyword, "max": 10},
                timeout=5
            )
            response.raise_for_status()
            return [item["word"] for item in response.json()]
        except Exception as e:
            logger.error(f"Datamuse-API-Fehler: {e}")
            return self.synonyms.get(keyword, [])

    def get_related_terms(self, keyword: str) -> List[str]:
        """Holt verwandte Begriffe von Wikipedia-API."""
        try:
            response = requests.get(
                "https://de.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": keyword,
                    "format": "json"
                },
                headers={"User-Agent": "kleinanzeigen-ai/1.0"},
                timeout=5
            )
            response.raise_for_status()
            titles = [item["title"] for item in response.json().get("query", {}).get("search", [])]
            return [title.split("–")[0] for title in titles]
        except Exception as e:
            logger.error(f"Wikipedia-API-Fehler: {e}")
            return self.related_terms.get(keyword, [])

    def get_trending_terms(self, keyword: str) -> List[str]:
        """Holt Trends von Google Trends (Scraping)."""
        try:
            pytrends = TrendReq(hl='de-DE', tz=360)
            pytrends.build_payload(kw_list=[keyword])
            related = pytrends.related_queries()
            top_queries = related.get(keyword, {}).get("top", [])
            if isinstance(top_queries, list):
                return [query["query"] for query in top_queries[:10]]
            elif isinstance(top_queries, str):
                # Falls die Daten als String zurückgegeben werden, parsen wir sie
                top_queries = eval(top_queries)
                return [query["query"] for query in top_queries[:10]]
            else:
                # Falls die Daten als DataFrame zurückgegeben werden
                return top_queries["query"].tolist()[:10]
        except Exception as e:
            logger.error(f"Google Trends-Scraping-Fehler: {e}")
            return []

    def get_suggestions(self, query: str) -> Dict[str, List[str]]:
        """Generiert Suchvorschläge für eine Nutzeranfrage."""
        if query in self.cache:
            return self.cache[query]

        keywords = query.split()
        suggestions = {}

        for keyword in keywords:
            synonyms = self.get_synonyms(keyword)
            related_terms = self.get_related_terms(keyword)
            trending_terms = self.get_trending_terms(keyword)

            if synonyms:
                suggestions[f"Synonyme für '{keyword}'"] = synonyms
            if related_terms:
                suggestions[f"Verwandte Begriffe für '{keyword}'"] = related_terms
            if trending_terms:
                suggestions[f"Aktuelle Trends für '{keyword}'"] = trending_terms

        self.cache[query] = suggestions
        return suggestions


# Instanz des Moduls
smart_search = SmartSearchSuggestions()
smart_search = SmartSearchSuggestions()