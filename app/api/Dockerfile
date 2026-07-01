FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

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

# --proxy-headers + --forwarded-allow-ips="*" make uvicorn trust the
# X-Forwarded-Proto header set by Azure Container Apps' TLS ingress, so
# generated URLs and redirects use https:// instead of http:// (avoids
# browser "form is not secure" mixed-content warnings behind the proxy).
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
