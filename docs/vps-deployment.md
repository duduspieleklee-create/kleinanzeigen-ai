# VPS Deployment Guide

How to run kleinanzeigen-ai on your own Ubuntu 22.04 VPS with Docker. This is
the only supported production deployment path — see `docs/architecture.md`
for how it fits together with the CI/CD pipeline
(`.github/workflows/ci-cd.yml`): `lint` and `test` run on every push and
pull request, and a `deploy` job SSHes in here to pull, migrate and restart
on every push to `main`. Steps 1-9 below get the VPS ready for that job to
target; "Automated deploys via CI" further down covers the job itself.

## Hostname options

The app sets its login cookie with the `Secure` flag whenever
`ENVIRONMENT != dev` (`app/api/routers/auth.py`), and browsers silently drop
`Secure` cookies sent over plain HTTP — login will appear to succeed with no
error but nothing actually persists. So the site needs real HTTPS, which
means Caddy needs a hostname (Let's Encrypt won't issue a certificate for a
bare IP address). Pick one:

- **You own a domain** — point a DNS A record at the VPS's IP and use that
  domain.
- **You don't own a domain** — use a free wildcard-DNS hostname that just
  resolves back to your own IP, e.g. `<ip-with-dashes>.eu-cloud-xip.com`
  (also available as `.nip.io` / `.sslip.io`). No signup needed, and Caddy
  gets a genuine trusted Let's Encrypt certificate for it exactly like a real
  domain — no self-signed cert, no browser warning.
- **Neither** — fall back to a self-signed cert on the bare IP; see
  "Bare-IP fallback" below. You'll need to click through a browser warning
  and Google OAuth won't work (it requires a real redirect URI).

Either of the first two options also means you can turn on Google OAuth from
day one (see step 4) since you have a valid HTTPS hostname for the redirect
URI.

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
sudo ufw allow 443/tcp
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

# Leave empty if you're on the bare-IP fallback (no valid redirect URI to
# register). If you have a domain or wildcard-DNS hostname, you can set
# these now — see "Google OAuth" below.
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

### Google OAuth (optional, requires a hostname)

If you have a domain or wildcard-DNS hostname from "Hostname options" above,
register `https://<your-hostname>/auth/google/callback` as an authorized
redirect URI in Google Cloud Console, then fill in `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` above.

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

Copy the repo's Caddyfile into place, replacing the placeholder with your
actual domain or wildcard-DNS hostname, then reload:

```bash
sudo cp /opt/kleinanzeigen-ai/deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i 's/your-domain-or-xip-hostname/<your-hostname>/' /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

### Bare-IP fallback

If you have no hostname at all, replace the Caddyfile contents instead with:

```
:80 {
	redir https://{host}{uri} permanent
}

:443 {
	tls internal
	reverse_proxy 127.0.0.1:8000
}
```

`tls internal` makes Caddy self-sign a certificate since Let's Encrypt can't
issue one for a bare IP — your browser will show a certificate warning to
click through, but the connection is genuinely HTTPS so the login cookie
still works. Switch to a real hostname later by replacing this with the
single-block form above.

## 8. First login

Visit `https://<your-hostname>/` and log in with `APP_USERNAME` /
`APP_PASSWORD` **right away**. This creates the app's `User` row, which gets
id `1` in a fresh database — matching `SYSTEM_USER_ID=1` in `.env`. If Celery
Beat's first scheduled scrape (every 30 minutes) fires before this row
exists, it will fail on a foreign-key constraint, so do this step promptly
after step 6.

## 9. Verify

```bash
curl http://127.0.0.1:8000/healthz          # direct to the api container
curl https://<your-hostname>/healthz        # through Caddy
docker compose -f docker-compose.prod.yml logs -f worker beat
```

## Automated deploys via CI

Once the VPS is set up (steps 1-9 above), merges to `main` deploy
automatically: the `deploy` job in `.github/workflows/ci-cd.yml` SSHes in
and runs the same commands as the "Deploy an update" section below.

Add these to **GitHub → repository → Settings → Secrets and variables →
Actions**:

| Secret | Value |
|---|---|
| `VPS_HOST` | The VPS's hostname or IP |
| `VPS_USER` | The SSH user that owns `/opt/kleinanzeigen-ai` (must have `docker` group membership — the same user from steps 1-6) |
| `VPS_SSH_PASSWORD` | That user's SSH login password |

`VPS_PORT` is an optional secret if SSH doesn't listen on the default `22`.

## Day-2 operations

**Deploy an update:** happens automatically on every merge to `main` (see
above). To do it manually — e.g. to test a branch, or if CI is down:
```bash
cd /opt/kleinanzeigen-ai
./deploy/deploy.sh
```
This pulls, rebuilds the `api` image with the real `GIT_SHA`/`APP_VERSION`/
`BUILD_TIME` (so the version stamp in the UI footer matches what's actually
deployed, the same as the CI job does for `main`), runs migrations, then
restarts all services. Running the raw `docker compose build` command
yourself instead skips that and falls back to the Dockerfile's placeholder
values ("local"/"dev"/"unknown").

**View logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f api
```

**Back up the database (one-off):**
```bash
./deploy/backup.sh
```
Writes a gzip-compressed dump to `backups/<db>-<timestamp>.sql.gz` and deletes
anything in that directory older than `RETENTION_DAYS` (default 14). Override
`BACKUP_DIR` / `RETENTION_DAYS` as env vars if needed.

**Restore:**
```bash
gunzip -c backups/kleinanzeigen_ai-2026-07-04_030001.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db \
  psql -U kleinanzeigen kleinanzeigen_ai
```

## Automated backups

Run `deploy/backup.sh` nightly via cron. Edit the crontab for the user that
owns the deployment (the one with `docker` group membership):

```bash
crontab -e
```

Add a line running it at, e.g., 03:00 every day, logging output so cron
failures are visible:

```
0 3 * * * /opt/kleinanzeigen-ai/deploy/backup.sh >> /opt/kleinanzeigen-ai/backups/backup.log 2>&1
```

Backups land in `/opt/kleinanzeigen-ai/backups/` (gitignored — this directory
lives only on the VPS). Since it's local-disk-only, a lost or wiped VPS loses
the backups too; copy the directory off-box periodically (e.g. `scp` or
`rsync` to another machine) if you need protection against that.

## Adding a domain + HTTPS + Google OAuth later

1. Point a DNS A record at the VPS's IP.
2. Edit `/etc/caddy/Caddyfile`, replacing the hostname with your domain (drop
   the `tls internal` block entirely if you were on the bare-IP fallback):
   ```
   your-domain.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```
3. `sudo systemctl reload caddy` — Caddy automatically provisions and renews
   the Let's Encrypt certificate.
4. In Google Cloud Console, register
   `https://your-domain.com/auth/google/callback` as an authorized redirect
   URI, then set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`.
5. `docker compose -f docker-compose.prod.yml up -d api` to pick up the new
   env vars.
