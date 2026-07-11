FROM python:3.11-slim

WORKDIR /app

# Install Node.js (for Vite frontend build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Copy Python deps + install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy full project (needed for frontend/ build context)
COPY . .

# Build frontend assets (Vite -> app/api/static/main.js + style.css)
# Skips if frontend/ is absent (e.g. local builds without frontend dir).
RUN if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then \
      cd frontend && npm ci && npm run build && cd ..; \
    fi

# Build/version metadata — passed by the CI build job as --build-arg and
# exposed as env vars so the app can display the running version and /version
# can report it. Defaults keep local `docker build` working without args.
ARG GIT_SHA=local
ARG BUILD_NUMBER=0
ARG APP_VERSION=dev
ARG BUILD_TIME=unknown
ENV GIT_SHA=$GIT_SHA \
    BUILD_NUMBER=$BUILD_NUMBER \
    APP_VERSION=$APP_VERSION \
    BUILD_TIME=$BUILD_TIME

# Drop root privileges — run the app as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# --proxy-headers + --forwarded-allow-ips="*" make uvicorn trust the
# X-Forwarded-Proto header set by Cloud Run's TLS-terminating proxy, so
# generated URLs and redirects use https:// instead of http:// (avoids
# browser "form is not secure" mixed-content warnings behind the proxy).
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
