"""
Test-Skript für Google Trends-Scraping mit pytrends
"""

from pytrends.request import TrendReq

print("🔍 Testing Google Trends-Scraping...")

# Google Trends-Client initialisieren
pytrends = TrendReq(hl='de-DE', tz=360)

# Trends für "Gartenmöbel" abfragen
try:
    pytrends.build_payload(kw_list=['Gartenmöbel'])
    trends = pytrends.related_queries()
    print("📊 Trends für 'Gartenmöbel':")
    print(trends)
except Exception as e:
    print(f"❌ Fehler beim Abfragen der Trends: {e}")

# Top-Suchanfragen für "Gartenmöbel" abfragen
try:
    pytrends.build_payload(kw_list=['Gartenmöbel'])
    top_queries = pytrends.top_queries()
    print("\n🔝 Top-Suchanfragen für 'Gartenmöbel':")
    print(top_queries)
except Exception as e:
    print(f"❌ Fehler beim Abfragen der Top-Suchanfragen: {e}")

print("\n✅ Google Trends-Scraping-Test abgeschlossen!")