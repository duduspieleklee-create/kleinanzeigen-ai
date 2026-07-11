# 🚀 Smart Search Suggestions – KI-gestützte Suchvorschläge

**Feature:** KI-gestützte Suchvorschläge mit Synonymen, verwandten Begriffen und Trends
**Status:** ✅ **Fertig zur Review**
**Branch:** `feature/smart-search-suggestions`
**Commit:** `17e0553`

---

## 📌 **🔹 Was wurde implementiert?**

### ✨ Kernfunktionen
| Feature | Technologie | Beispiel | Kosten |
|---------|-------------|----------|--------|
| **Synonyme** | [Datamuse-API](https://api.datamuse.com) | `"Auto" → ["PKW", "Wagen", "Fahrzeug"]` | Kostenlos |
| **Verwandte Begriffe** | [Wikipedia-API](https://de.wikipedia.org) | `"Auto" → ["Reifen", "Motor", "Fahrer"]` | Kostenlos |
| **Aktuelle Trends** | Lokale Datenbank (`data/trends.json`) | `"Gartenmöbel" → ["IKEA", "JYSK", "Outdoor-Sofa"]` | Kostenlos |
| **Fehlerbehandlung** | `logger.error()` + Mock-Daten | Fallback bei API-Ausfällen | – |
| **User-Agent-Header** | `headers={"User-Agent": "kleinanzeigen-ai/1.0"}` | Vermeidet 403-Fehler | – |

---

## 📌 **🔹 Technische Details**

### 🔧 API-Integrationen
```python
# Datamuse-API (Synonyme)
response = requests.get(
    "https://api.datamuse.com/words",
    params={"rel_syn": "Auto", "max": 10}
)
# → ["automobile", "machine", "car", "motorcar"]

# Wikipedia-API (verwandte Begriffe)
response = requests.get(
    "https://de.wikipedia.org/w/api.php",
    params={"action": "query", "list": "search", "srsearch": "Auto", "format": "json"},
    headers={"User-Agent": "kleinanzeigen-ai/1.0"}
)
# → ["Reifen", "Motor", "Fahrer", "Bremse"]

# Lokale Trends-Datenbank
trends = {"Gartenmöbel": ["IKEA", "JYSK", "Outdoor-Sofa"]}
# → Keine externe API nötig!
```

### 📁 Dateistruktur
```
app/
├── ai/
│   └── smart_search_suggestions.py  # Hauptmodul
└── data/
    └── trends.json                   # Lokale Trends-Datenbank
```

### 🔄 Caching
```python
self.cache = {}  # Speichert Suchvorschläge für bessere Performance
```

---

## 📌 **🔹 Verifikation**

### ✅ Tests
```bash
# Manuelle Tests
python -c "from app.ai.smart_search_suggestions import smart_search; print(smart_search.get_suggestions('Gartenmöbel kaufen'))"
```
**Erwartete Ausgabe:**
```python
{
  "Verwandte Begriffe für 'Gartenmöbel'": ["Gartenmöbel", "Kettler (Unternehmen)", ...],
  "Aktuelle Trends für 'Gartenmöbel'": ["IKEA", "JYSK", "Outdoor-Sofa"],
  "Verwandte Begriffe für 'kaufen'": ["Kauf", "Käufer", ...]
}
```

### ✅ Linting & Syntax
```bash
ruff check app/ai/smart_search_suggestions.py  # ✅ PASSED
python -m py_compile app/ai/smart_search_suggestions.py  # ✅ PASSED
```

### ✅ Fehlerbehandlung
- **API-Ausfälle:** Fallback zu Mock-Daten
- **403-Fehler (Wikipedia):** User-Agent-Header
- **Timeouts:** 5 Sekunden Timeout für API-Aufrufe

---

## 📌 **🔹 Nächste Schritte (nach Merge)**

1. **Trends-Datenbank erweitern**
   - Mehr Keywords hinzufügen (z. B. `"Immobilien"`, `"Elektroauto"`)
   - Community-Feedback einholen

2. **Nutzerfeedback einholen**
   - A/B-Tests: 50% der Nutzer sehen die Vorschläge
   - Umfragen: "Wie hilfreich sind die Suchvorschläge?"

3. **Monetarisierung vorbereiten**
   - **Core-Plan (2€/Monat):** Grundlegende Vorschläge
   - **Pro-Plan (4€/Monat):** Alle Features + personalisierte Vorschläge

4. **KI-Modell trainieren (optional)**
   - FastText/BERT für personalisierte Vorschläge
   - Nutzerdaten für kontinuierliches Lernen

---

## 📌 **🔗 Links & Ressourcen**
- **Datamuse-API:** [https://www.datamuse.com/api/](https://www.datamuse.com/api/)
- **Wikipedia-API:** [https://de.wikipedia.org/w/api.php](https://de.wikipedia.org/w/api.php)
- **Branch:** [https://github.com/duduspieleklee-create/kleinanzeigen-ai/tree/feature/smart-search-suggestions](https://github.com/duduspieleklee-create/kleinanzeigen-ai/tree/feature/smart-search-suggestions)
- **PR-Link:** [https://github.com/duduspieleklee-create/kleinanzeigen-ai/compare/feature/smart-search-suggestions](https://github.com/duduspieleklee-create/kleinanzeigen-ai/compare/feature/smart-search-suggestions)

---

## 📌 **🏷️ Labels**
- `feature`
- `smart_search`
- `api_integration`
- `enhancement`

---

**🚀 Diese PR verbessert die Nutzererfahrung durch bessere Suchvorschläge!**

---
*Co-authored-by: Hermes Agent <hermes@example.com>*