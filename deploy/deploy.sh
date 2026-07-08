#!/usr/bin/env bash
# Manual deploy/redeploy: pulls, migrates, and rebuilds with the real
# GIT_SHA/APP_VERSION/BUILD_TIME baked in (see "Day-2 operations" in
# docs/vps-deployment.md). Run this instead of the raw docker compose
# commands so the version stamp in the UI footer reflects what's actually
# running, the same way the CI deploy job (.github/workflows/ci-cd.yml)
# does for merges to main.
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

git checkout main
git branch --set-upstream-to=origin/main main
git pull

export GIT_SHA="$(git rev-parse HEAD)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export APP_VERSION="$(grep -m1 '^version' pyproject.toml | sed -E 's/version = "(.*)"/\1/')"
export BUILD_NUMBER="${BUILD_NUMBER:-0}"

run() {
  echo "+ $*"
  if [ "$DRY_RUN" -ne 1 ]; then
    "$@"
  fi
}

previous_git_sha=""
if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
  previous_git_sha="$(git rev-parse HEAD~1)"
else
  previous_git_sha="$(git rev-parse HEAD)"
fi
previous_build_time="$(git show -s --format=%ci "$previous_git_sha" 2>/dev/null | awk '{print $4}' || echo 'unknown')"
previous_app_version="$APP_VERSION"
previous_build_number="$((BUILD_NUMBER - 1))"
if [ "$previous_build_number" -lt 0 ]; then
  previous_build_number=0
fi

run docker compose -f docker-compose.prod.yml build api
run docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
run docker compose -f docker-compose.prod.yml up -d --build

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run complete; no containers were changed."
  exit 0
fi

# Post-deploy smoke checks: must match the new build args.
set +e
for i in $(seq 1 60); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/healthz" 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    break
  fi
  sleep 2
done
HEALTH=$(curl -s "http://127.0.0.1:8000/healthz" 2>/dev/null || echo '{}')
VERSION=$(curl -s "http://127.0.0.1:8000/version" 2>/dev/null || echo '{}')
set -e

if ! echo "$HEALTH" | grep -q '"status":"ok"'; then
  echo "FAIL: /healthz did not return ok: $HEALTH"
  run git checkout "$previous_git_sha"
  export GIT_SHA="$previous_git_sha"
  export BUILD_TIME="$previous_build_time"
  export APP_VERSION="$previous_app_version"
  export BUILD_NUMBER="$previous_build_number"
  run docker compose -f docker-compose.prod.yml build api
  run docker compose -f docker-compose.prod.yml up -d --build
  exit 1
fi
if ! echo "$VERSION" | grep -q "\"commit\":\"${GIT_SHA}\""; then
  echo "FAIL: /version commit mismatch. got=$VERSION expected=$GIT_SHA"
  exit 1
fi
if ! echo "$VERSION" | grep -q "\"version\":\"${APP_VERSION}\""; then
  echo "FAIL: /version version mismatch. got=$VERSION expected=$APP_VERSION"
  exit 1
fi
if ! echo "$VERSION" | grep -q "\"build\":\"${BUILD_NUMBER}\""; then
  echo "FAIL: /version build mismatch. got=$VERSION expected=$BUILD_NUMBER"
  exit 1
fi
echo "Deploy smoke checks passed: healthz=ok version=$VERSION"
