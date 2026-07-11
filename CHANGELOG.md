# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Smart Search Suggestions (Feature)**
  - KI-gestützte Suchvorschläge für Nutzer (Synonyme, verwandte Begriffe)
  - API-Endpunkt für Suchvorschläge (`GET /api/search-suggestions`)
  - Frontend-Komponente für Suchvorschläge
  - Datenbank-Tabelle für Suchvorschläge und deren Nutzungshäufigkeit
  - Custom Model Endpoint (OpenAI-kompatibel) für KI-Vorschläge
    (`CUSTOM_MODEL_ENDPOINT`/`CUSTOM_MODEL_NAME`, optional, mit Fallback)

### Changed
- Keine Änderungen

### Fixed
- Navigationsfix: 'Meine Ergebnisse'-Tab mit Map-Button (Issue #223)
- Deploy-Race beim VPS-Update behoben: `git pull` durch `git fetch` + `git reset --hard origin/main` ersetzt (vermeidet divergent-branch-Abbrüche)
- Alembic-Migration: doppelte Index-Erzeugung in `fraud_alerts`/`search_suggestions` entfernt (brach `mobile`/`deploy` auf frischer DB)
- Smart-Search-Tests deterministisch gemacht (Netzwerk-Mock), da Live-Datamuse/Wikipedia-Calls die hartkodierten Mock-Daten überschrieben
- Orphaned 'running' Recurring-Search-Tasks mit `last_run_at=NULL` werden vom Reaper erkannt und revived (Fixes #217)
- Resend-Key-Ausfall: nicht-blockierendes Banner + selbst-diagnostizierende Logs (Fixes #237)
- PWA: branded Icons regeneriert, tote Sound-Datei, deutsche Offline-Seite, iOS-Icon (Fixes #227)
- PWA: sichtbarer Install-Button + iOS-Manual-Add-Pfad (Fixes #235)
- Suchergebnis-Map als Pro-Feature abgegrenzt (Fixes #225)
- Wizard: Interval-Optionen nach Tarif gestaffelt (Fixes #224)

---

## [1.0.0] - 2026-07-11

### Added
- Erste Version von kleinanzeigen-ai
