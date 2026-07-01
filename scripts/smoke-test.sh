#!/usr/bin/env bash
# Run before pushing to catch import errors and startup crashes locally.
# Usage: ./scripts/smoke-test.sh
set -euo pipefail

export DATABASE_URL="postgresql://ci:ci@localhost/ci"
export SECRET_KEY="ci-test-secret"
export REDIS_URL="redis://localhost:6379/0"

echo "==> Checking imports..."
python -c "from app.api.main import app; print('  API OK')"
python -c "from app.worker.celery_app import celery_app; print('  Worker OK')"
python -c "from app.beat.celery_beat import celery_app; print('  Beat OK')"

echo "==> Starting API..."
uvicorn app.api.main:app --host 127.0.0.1 --port 8765 &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null" EXIT

for i in $(seq 1 15); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/healthz || echo "000")
  [ "$STATUS" = "200" ] && break
  sleep 1
done

STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/healthz)
if [ "$STATUS" != "200" ]; then
  echo "FAIL: /healthz returned $STATUS"
  exit 1
fi

echo "==> All checks passed"
