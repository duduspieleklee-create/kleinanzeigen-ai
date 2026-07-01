FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# --proxy-headers + --forwarded-allow-ips="*" make uvicorn trust the
# X-Forwarded-Proto header set by Azure Container Apps' TLS ingress, so
# generated URLs and redirects use https:// instead of http:// (avoids
# browser "form is not secure" mixed-content warnings behind the proxy).
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
