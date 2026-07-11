#!/usr/bin/env bash
curl -s http://localhost:8000/smart_search?query=Auto kaufen | python3 -c "
import sys
import json

# JSON auscurl auslesen
response = sys.stdin.read()

# JSON parsen
try:
    data = json.loads(response)
    print(f'Smart Search Vorschläge: {data.get("suggestions", "Keine Vorschläge")}')
except json.JSONDecodeError:
    print(f'Fehler: {response}')
"