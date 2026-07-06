# Review des Repositories `kleinanzeigen-ai`

## Überblick

Das Repository `kleinanzeigen-ai` ist eine auf Python basierende, mehrteilige Anwendung (Multi-Service-Architektur), die speziell für die Automatisierung und KI-gestützte Überwachung von Anzeigen auf der Plattform kleinanzeigen.de entwickelt wurde. Die Anwendung ermöglicht es Benutzern, strukturierte Suchanfragen zu definieren, diese in regelmäßigen Abständen auszuführen und bei relevanten neuen Anzeigen (die den Suchkriterien entsprechen) benachrichtigt zu werden.

Die Lösung ist modern aufgebaut und verwendet aktuelle Python-Technologien. Sie besteht im Wesentlichen aus einer REST-API mit Web-Frontend, einem asynchronen Worker für das Scraping und einem Scheduler für wiederkehrende Aufgaben.

## Architektur und Komponenten

Das System ist in drei Hauptkomponenten unterteilt, die über Docker Compose orchestriert werden und gemeinsam auf eine PostgreSQL-Datenbank und einen Redis-Cache zugreifen:

1. **API & Web UI (`app/api`)**:
   Basierend auf **FastAPI** stellt diese Komponente sowohl die REST-Schnittstellen als auch ein serverseitig gerendertes Web-Frontend (mit Jinja2-Templates) bereit. Die Authentifizierung erfolgt über Google OAuth. Hier verwalten die Nutzer ihre Suchaufträge, sehen Ergebnisse ein und konfigurieren ihre Einstellungen (inkl. Stripe-Billing für bezahlte Pläne).

2. **Worker (`app/worker`)**:
   Ein **Celery-Worker**, der die rechenintensiven und zeitaufwändigen Scraping-Aufgaben asynchron abarbeitet. Er ruft die URLs von kleinanzeigen.de ab, parst das HTML mittels `BeautifulSoup` und speichert die extrahierten Anzeigen als `ScrapeResult` in der Datenbank. Um Blockierungen zu vermeiden, ist eine Unterstützung für rotierende Proxys integriert.

3. **Beat Scheduler (`app/beat`)**:
   Ein **Celery Beat**-Prozess, der zeitgesteuerte Aufgaben auslöst. Er sorgt dafür, dass systemweite oder vom Administrator konfigurierte Suchanfragen in regelmäßigen Abständen (z.B. jede Minute) in die Queue gestellt werden.

4. **Shared Library (`app/shared`)**:
   Gemeinsam genutzter Code, darunter die SQLAlchemy-Datenbankmodelle, Preis-Analyse-Logik (`pricing.py`), Proxy-Verwaltung und die Definition der verschiedenen Abonnement-Pläne (`plans.py`).

## Datenmodell und Datenbank

Als Datenbank kommt **PostgreSQL** zum Einsatz. Das Schema wird strikt über **Alembic**-Migrationen versioniert und verwaltet. Das zentrale Datenmodell umfasst:

* **User**: Speichert Benutzerdaten, Google OAuth-Informationen, den aktuellen Plan (Basic, Core, Pro) und Stripe-Abonnement-Details.
* **ScrapeTask**: Repräsentiert einen Suchauftrag eines Benutzers. Enthält Parameter wie Suchbegriffe, Preisgrenzen und das Intervall für wiederkehrende Suchen. Ein Task durchläuft verschiedene Status (pending → running → completed/failed).
* **ScrapeResult**: Eine einzelne gefundene Anzeige, die mit einem `ScrapeTask` verknüpft ist. Speichert Titel, Preis, Ort, Bild-URL und den Veröffentlichungszeitpunkt.
* **AdminSearch**: Globale, vom Administrator definierte Suchanfragen.
* **Proxy & SystemSetting**: Konfiguration für rotierende Proxys, um IP-Banns beim Scraping zu umgehen.

## Features und Geschäftslogik

Das Projekt enthält eine beachtliche Menge an Features, die über ein reines Scraping-Skript hinausgehen und eher in Richtung eines SaaS-Produkts (Software as a Service) deuten:

* **Authentifizierung**: E-Mail/Passwort (mit Verifizierungs-Mail über Resend) und Google OAuth 2.0, beide münden im selben JWT-Cookie. Ein Settings-basierter Bootstrap-Admin-Login existiert zusätzlich, um das allererste Admin-Konto anzulegen, ist aber hinter `BOOTSTRAP_ADMIN_ENABLED` und einer Mindestpasswortlänge außerhalb von `dev` abgesichert.
* **Abonnement-System (Stripe)**: Integration mit Stripe Webhooks. Es gibt verschiedene Pläne (Basic, Core, Pro), die sich in der Anzahl der aktiven Suchen, den wöchentlichen Credits und dem minimalen Suchintervall (bis zu 60 Sekunden im Pro-Plan) unterscheiden. Die Logik behandelt auch Downgrades sauber (z.B. Drosselung oder Stornierung überzähliger Suchen). Die Preisseite (`/billing`) und eine neue öffentliche Landingpage (`/`) sind jetzt auch ohne Login einsehbar.
* **Markt-Intelligenz**: Die Datei `pricing.py` analysiert die Preise der gefundenen Anzeigen, berechnet den Median und versieht die Ergebnisse mit "Deal Badges" (z.B. "15% below market" oder "Fair price") sowie einem Trust Score pro Verkäufer.
* **Benachrichtigungen**: Web Push (via `pywebpush`, inkl. Ruhezeiten und Geräteverwaltung unter `/settings`) und optional E-Mail über Resend — beide feuern am selben Punkt (neue, nicht-Baseline-Treffer) und respektieren dieselben Nutzereinstellungen.
* **Konto & Datenschutz**: Nutzer können ihre Daten als JSON exportieren und ihr Konto vollständig löschen (`/settings/export`, `/settings/delete-account`) — DSGVO Art. 15/17/20. Eine tägliche Aufräum-Aufgabe (Celery Beat) löscht Suchergebnisse nach 14 Tagen und Token-Nutzungsdaten nach 90 Tagen.
* **Admin-Oberfläche**: Verwaltung globaler Hintergrundsuchen (`AdminSearch`) und eines rotierenden Proxy-Pools (mit SSRF-Schutz) direkt im Dashboard (`#tab-admin`).
* **CI/CD & Deployment**: GitHub Actions (`.github/workflows/ci-cd.yml`) lintet und testet jeden Push/PR und deployed bei jedem Push auf `main` per SSH auf einen selbstverwalteten VPS (Docker Compose + Caddy) — kein GCP/Cloud Run, kein Azure Container Registry mehr im Einsatz.

## Aktueller Entwicklungsstand

Das Repository ist sehr aktiv (über 460 Commits, Stand 2026-07-06). Ein Code-Audit auf Kommerzialisierungsreife deckte im Juli 2026 mehrere Lücken zwischen Anspruch und tatsächlichem Verhalten auf — unter anderem eine defekte Onboarding-Tutorial-Route, komplett wirkungslose E-Mail-Benachrichtigungen, eine nie eingeplante Datenlöschroutine, eine fehlende Konto-Löschfunktion und eine unerreichbare Admin-Oberfläche. Alle wurden im selben Zug behoben (siehe `TODO.txt`, Eintrag 30). Davor lag der Fokus auf:
* Deutsche Übersetzung der Oberfläche.
* Ein "Smart Enhancements" Wizard für die Sucherstellung.
* Verbesserungen auf der Ergebnisseite (Pagination, Location-Tabs, "NEW"-Badges basierend auf dem letzten Besuch).
* Die Alembic-Migrationen (aktuell Version `0019`) zeigen, dass das Datenmodell kontinuierlich erweitert wird (u.a. Trial-Tracking, Tutorial-Flag, Benachrichtigungseinstellungen).

## Fazit

Das Repository `kleinanzeigen-ai` ist eine sehr gut strukturierte, professionell aufgebaute SaaS-Anwendung, die inzwischen produktiv läuft. Die Trennung in API, Worker und Scheduler mittels FastAPI und Celery ist eine bewährte und skalierbare Architektur für Scraping-Workloads. Besonders hervorzuheben sind die integrierte Geschäftslogik (Stripe-Billing, Plan-Enforcement) und die analytischen Funktionen (Deal-Scoring, Trust Score), die dem Nutzer einen echten Mehrwert gegenüber der normalen Plattform bieten. Die im Juli-Audit gefundenen Lücken betrafen durchgehend die Schicht *um* das Produkt herum — Onboarding, Compliance, Admin-Bedienbarkeit — nicht die Kernarchitektur, und sind inzwischen geschlossen.
