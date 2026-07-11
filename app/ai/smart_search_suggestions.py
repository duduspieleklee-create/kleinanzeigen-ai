"""
Smart Search Suggestions – KI-Modul für kleinanzeigen-ai
Zweck: Generiert Suchvorschläge basierend auf Nutzeranfragen.
"""

from typing import List, Dict


class SmartSearchSuggestions:
    """
    KI-Modul für intelligente Suchvorschläge.
    """

    def __init__(self):
        # Mock-Daten für Demo-Zwecke
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
        """
        Holt Synonyme für ein Keyword (z. B. "Auto" → ["PKW", "Wagen", "Fahrzeug"]).
        """
        return self.synonyms.get(keyword, [])

    def get_related_terms(self, keyword: str) -> List[str]:
        """
        Holt verwandte Begriffe für ein Keyword (z. B. "Auto" → ["Reifen", "Motor", "Fahrer"]).
        """
        return self.related_terms.get(keyword, [])

    def get_suggestions(self, query: str) -> Dict[str, List[str]]:
        """
        Generiert Suchvorschläge für eine Nutzeranfrage.
        """
        if query in self.cache:
            return self.cache[query]

        # Keywords aus der Suchanfrage extrahieren
        keywords = query.split()
        suggestions = {}

        for keyword in keywords:
            synonyms = self.get_synonyms(keyword)
            related_terms = self.get_related_terms(keyword)

            if synonyms:
                suggestions[f"Synonyme für '{keyword}'"] = synonyms
            if related_terms:
                suggestions[f"Verwandte Begriffe für '{keyword}'"] = related_terms

        self.cache[query] = suggestions
        return suggestions


# Instanz des Moduls
smart_search = SmartSearchSuggestions()