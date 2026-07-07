# Cloudflare Turnstile

Turnstile is a CAPTCHA-style challenge that protects the **public,
unauthenticated forms** — login and register — against bots,
credential-stuffing and automated signups. The browser renders an invisible
(or interactive) widget; on submit it adds a token to the form, and the server
validates that token with Cloudflare before trusting the request.

Reference: <https://developers.cloudflare.com/turnstile/>

## Configuration keys

Get both from the Cloudflare dashboard → **Turnstile → Add site**:

| Key | Public? | Used for |
|---|---|---|
| `TURNSTILE_SITE_KEY` | **Yes** — rendered into the HTML | Tells the browser widget which site config to load |
| `TURNSTILE_SECRET_KEY` | **No — keep secret** | Server-side validation via the siteverify API |

Both must be set for Turnstile to activate. If **either** is empty, Turnstile
is disabled and the forms submit without a challenge (so local/dev works with
no keys). This is the `settings.turnstile_enabled` gate in
`app/api/config.py`.

## Where each piece lives, and why

| What | File | Why here |
|---|---|---|
| The two settings + `turnstile_enabled` property | `app/api/config.py` | All config flows through one `pydantic_settings` object; nothing reads env vars directly. |
| Server-side siteverify call | `app/api/turnstile.py` | One small, reusable, testable helper. Async (routes are `async`), uses `httpx`, and **fails closed** — a missing/invalid token or a network error returns `False`. |
| Token check in the handlers | `app/api/routers/auth.py` (`POST /auth/login`, `POST /auth/register`) | These are the only unauthenticated, abusable POST endpoints. The check runs **first**, before any DB work; on failure the form re-renders with an error. |
| The widget + `api.js` script | `app/api/templates/login.html`, `register.html` | Rendered only when a site key is present (`{% if turnstile_site_key %}`), so the pages are unchanged when Turnstile is off. |
| `turnstile_site_key` template global | `app/api/version.py` (`register_globals`) | The site key is public and needed by several templates; exposing it as a Jinja global avoids threading it through every route's context. |
| CSP allowances for `challenges.cloudflare.com` | `app/api/main.py` (security middleware) | The strict CSP would otherwise block Turnstile's script and iframe. Added to `script-src`, `frame-src` and `connect-src`. |

Only login and register are covered on purpose: every other state-changing
endpoint is already behind authentication + rate limiting, so a challenge there
adds friction without a matching security gain. The helper in
`app/api/turnstile.py` is generic, so adding Turnstile elsewhere later is a
two-line change.

## Where to put the key values

Turnstile reads its keys from the environment like every other setting — see
`app/api/config.py`. Two supported ways:

1. **Directly in `.env`** (simplest). Add:
   ```dotenv
   TURNSTILE_SITE_KEY=0x...
   TURNSTILE_SECRET_KEY=0x...
   ```
   `.env` is gitignored, so the secret never enters the repo. Restart the API
   container to pick up the change (`docker compose ... up -d --force-recreate api`).
   - **prod** (`docker-compose.prod.yml`) injects `.env` via `env_file: .env`.
   - **dev** (`docker-compose.yml`) mounts the repo, and the app reads `/app/.env`
     directly.

2. **As GitHub repo secrets** (recommended for the secret key). The `deploy`
   job in `.github/workflows/ci-cd.yml` writes `TURNSTILE_SITE_KEY` and
   `TURNSTILE_SECRET_KEY` from repo secrets into the server's `.env` on every
   deploy to `main`, mirroring how `RESEND_API_KEY` is handled. A repo secret
   does nothing on its own — it only reaches the app because the workflow
   writes it into `.env`. Add them under
   **GitHub → Settings → Secrets and variables → Actions**. Both are optional;
   the injection step is skipped when the secret is unset.

The two methods coexist: `git pull` never touches `.env`, and the deploy script
only rewrites the specific keys whose secret is set.

## Testing without real traffic

Cloudflare publishes dummy keys that always pass or always fail — handy for
local checks (see
<https://developers.cloudflare.com/turnstile/troubleshooting/testing/>):

| Purpose | Site key | Secret key |
|---|---|---|
| Always passes | `1x00000000000000000000AA` | `1x0000000000000000000000000000000AA` |
| Always blocks | `2x00000000000000000000AB` | `2x0000000000000000000000000000000AA` |
