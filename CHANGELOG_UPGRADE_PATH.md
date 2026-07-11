# Upgrade-Pfad Feature

## [Unreleased]

### Added
- **Upgrade-Banner** (nicht-intrusiv, Top der Seite) für Free-Nutzer
- **Plan-Vergleichstabelle** (Settings → Abos) mit Feature-Vergleich Free vs. Core
- **Tooltip auf Free-Features** (z. B. Suchleiste) mit Upgrade-Hinweis
- **Checkout-Modal** mit 3 Preis-Tiers (Basic, Pro, Business) und Zahlungsoptionen (Stripe, PayPal, Krypto, SEPA)
- **E-Mail-Serie** für Upgrade-Erinnerungen (Tag 1, 3, 7)
- **Gamification:** Fortschrittsbalken und Rabattcode nach 7 Tagen Free-Nutzung
- **A/B-Testing:** Varianten A (Kontrolle) und B (sozialer Beweis)
- **Analytics-Integration** (Google Analytics 4, Mixpanel)

### Changed
- Default-Modell in `config.yaml` auf `tencent/hy3:free` korrigiert (Issue #241 behoben)

### Notes
- Alle Änderungen sind rückwärtskompatibel und nur für Free-Nutzer sichtbar.
- Keine Datenmigration nötig — Nutzer behalten ihre gespeicherten Suchen.
