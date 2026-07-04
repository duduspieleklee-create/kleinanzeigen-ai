# VPS Deployment Guide

How to run kleinanzeigen-ai on your own Ubuntu 22.04 VPS with Docker, starting
IP-only (no domain yet) and using the built-in username/password login instead
of Google OAuth. See "Adding a domain" at the end for upgrading later.

This is a separate path from the Cloud Run deployment described in
`docs/architecture.md` and `.github/workflows/build-and-push.yml` — nothing
here touches that pipeline.

## Why IP-only skips Google OAuth

Google OAuth requires a registered redirect URI, and Google does not accept a
bare IP address for one. Until you have a domain, leave `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` empty in `.env` — this disables the "Sign in with
Google" button (see the comment in `app/api/config.py`) and you log in with
the app's own `APP_USERNAME` / `APP_PASSWORD` credentials instead.

## 1. Prerequisites

SSH into the VPS and confirm Docker is ready:

```bash
docker --version
docker compose version
```

If `docker compose version` fails (only the legacy standalone `docker-compose`
is installed), add the plugin:

```bash
sudo apt update
sudo apt install -y docker-compose-plugin git
```

## 2. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw enable
```

Postgres and Redis are never published to the host in the production compose
file (see below), so there's nothing to open for them.

## 3. Get the code

```bash
sudo mkdir -p /opt/kleinanzeigen-ai
sudo chown "$USER" /opt/kleinanzeigen-ai
git clone <your-repo-url> /opt/kleinanzeigen-ai
cd /opt/kleinanzeigen-ai
git checkout claude/deploy-ubuntu-vps-docker-39lc9p   # or main, once merged
```

## 4. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and set these for production:

```bash
ENVIRONMENT=production

# Generate a real secret — the app refuses to boot outside dev with the
# default or with anything under 32 characters (app/api/config.py).
SECRET_KEY=$(openssl rand -hex 32)

# Change these from the built-in defaults (admin / KaSearch2026) — the app
# also refuses to boot in production with the default APP_PASSWORD.
APP_USERNAME=<pick-a-username>
APP_PASSWORD=<pick-a-strong-password>

# Postgres credentials used by docker-compose.prod.yml's db service.
# DATABASE_URL's password must match POSTGRES_PASSWORD exactly.
POSTGRES_USER=kleinanzeigen
POSTGRES_PASSWORD=<pick-a-strong-password>
POSTGRES_DB=kleinanzeigen_ai
DATABASE_URL=postgresql://kleinanzeigen:<same-password-as-above>@db:5432/kleinanzeigen_ai

REDIS_URL=redis://redis:6379/0

# Leave empty for the IP-only phase (see "Why IP-only skips Google OAuth").
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

SYSTEM_USER_ID=1
```

Everything else in `.env.example` (`VAPID_*`, `STRIPE_*`, `RESEND_API_KEY`,
`BEAT_KEYWORDS`/`BEAT_LOCATION`/`BEAT_PRICE_MAX`, `ALLOWED_EMAILS`,
`ADMIN_EMAILS`) can stay at its default/empty value — those features are
optional and disable themselves cleanly when unset.

`openssl rand -hex 32` prints straight to stdout; paste the result into
`SECRET_KEY=` in the file rather than relying on the `$(...)` substitution
above if you're editing `.env` directly instead of through a shell.

## 5. Run database migrations

Start just the database, then run the one-off migration container (schema is
managed exclusively through Alembic — see `docs/alembic.md`):

```bash
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

## 6. Start the full stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

All five containers (`db`, `redis`, `api`, `worker`, `beat`) should show as
running/healthy.

## 7. Install and configure Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Copy the repo's Caddyfile into place and reload:

```bash
sudo cp /opt/kleinanzeigen-ai/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 8. First login

Visit `http://<your-vps-ip>/` and log in with `APP_USERNAME` / `APP_PASSWORD`
**right away**. This creates the app's `User` row, which gets id `1` in a
fresh database — matching `SYSTEM_USER_ID=1` in `.env`. If Celery Beat's
first scheduled scrape (every 30 minutes) fires before this row exists, it
will fail on a foreign-key constraint, so do this step promptly after step 6.

## 9. Verify

```bash
curl http://127.0.0.1:8000/healthz          # direct to the api container
curl http://<your-vps-ip>/healthz           # through Caddy
docker compose -f docker-compose.prod.yml logs -f worker beat
```

## Day-2 operations

**Deploy an update:**
```bash
cd /opt/kleinanzeigen-ai
git pull
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d --build
```

**View logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f api
```

**Back up the database:**
```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U kleinanzeigen kleinanzeigen_ai > backup-$(date +%F).sql
```

**Restore:**
```bash
cat backup-2026-07-04.sql | docker compose -f docker-compose.prod.yml exec -T db \
  psql -U kleinanzeigen kleinanzeigen_ai
```

## Adding a domain + HTTPS + Google OAuth later

1. Point a DNS A record at the VPS's IP.
2. Edit `/etc/caddy/Caddyfile`, replacing `:80` with your domain:
   ```
   your-domain.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```
3. `sudo systemctl reload caddy` — Caddy automatically provisions and renews
   a Let's Encrypt certificate.
4. In Google Cloud Console, register
   `https://your-domain.com/auth/google/callback` as an authorized redirect
   URI, then set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`.
5. `docker compose -f docker-compose.prod.yml up -d api` to pick up the new
   env vars.
