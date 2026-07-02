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

* **Authentifizierung**: Google OAuth 2.0 Integration.
* **Abonnement-System (Stripe)**: Integration mit Stripe Webhooks. Es gibt verschiedene Pläne (Basic, Core, Pro), die sich in der Anzahl der aktiven Suchen, den wöchentlichen Credits und dem minimalen Suchintervall (bis zu 60 Sekunden im Pro-Plan) unterscheiden. Die Logik behandelt auch Downgrades sauber (z.B. Drosselung oder Stornierung überzähliger Suchen).
* **Markt-Intelligenz**: Die Datei `pricing.py` analysiert die Preise der gefundenen Anzeigen, berechnet den Median und versieht die Ergebnisse mit "Deal Badges" (z.B. "15% below market" oder "Fair price").
* **Push-Benachrichtigungen**: Nutzer können sich über neue, relevante Anzeigen direkt im Browser benachrichtigen lassen (Web Push via `pywebpush`).
* **CI/CD & Deployment**: Ein vollständiger GitHub Actions Workflow (`build-and-push.yml`) baut die Docker-Images, pusht sie in eine Azure Container Registry (ACR) und bereitet das Deployment via Octopus Deploy vor.

## Aktueller Entwicklungsstand

Das Repository ist sehr aktiv. Es gibt 367 Commits, und die letzten Commits (Merge von Pull Request #36) deuten auf einen starken Fokus auf die Benutzeroberfläche (Dashboard) hin. Zuletzt wurden unter anderem folgende Verbesserungen vorgenommen:
* Deutsche Übersetzung der Oberfläche.
* Ein "Smart Enhancements" Wizard für die Sucherstellung.
* Verbesserungen auf der Ergebnisseite (Pagination, Location-Tabs, "NEW"-Badges basierend auf dem letzten Besuch).
* Die Alembic-Migrationen (aktuell Version `0014`) zeigen, dass das Datenmodell kontinuierlich um Features wie Trial-Tracking und Basis-Scrapes erweitert wird.

## Fazit

Das Repository `kleinanzeigen-ai` ist eine sehr gut strukturierte, professionell aufgebaute SaaS-Anwendung. Die Trennung in API, Worker und Scheduler mittels FastAPI und Celery ist eine bewährte und skalierbare Architektur für Scraping-Workloads. Besonders hervorzuheben sind die integrierte Geschäftslogik (Stripe-Billing, Plan-Enforcement) und die analytischen Funktionen (Deal-Scoring), die dem Nutzer einen echten Mehrwert gegenüber der normalen Plattform bieten.
