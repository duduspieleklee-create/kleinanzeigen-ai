"""No-op TCP listener on $PORT so Cloud Run's startup probe succeeds for
background services (Celery worker/beat) that don't otherwise serve HTTP.
Run alongside the real process: `python -m app.shared.health_shim &`.
"""
import http.server
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    http.server.HTTPServer(("0.0.0.0", port), http.server.BaseHTTPRequestHandler).serve_forever()
