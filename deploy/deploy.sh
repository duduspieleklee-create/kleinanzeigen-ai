#!/usr/bin/env bash
# Manual deploy/redeploy: pulls, migrates, and rebuilds with the real
# GIT_SHA/APP_VERSION/BUILD_TIME baked in (see "Day-2 operations" in
# docs/vps-deployment.md). Run this instead of the raw docker compose
# commands so the version stamp in the UI footer reflects what's actually
# running, the same way the CI deploy job (.github/workflows/ci-cd.yml)
# does for merges to main.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

git checkout main
git branch --set-upstream-to=origin/main main
git pull

export GIT_SHA="$(git rev-parse HEAD)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export APP_VERSION="$(grep -m1 '^version' pyproject.toml | sed -E 's/version = "(.*)"/\1/')"
export BUILD_NUMBER="${BUILD_NUMBER:-0}"

docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d --build
