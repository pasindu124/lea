#!/usr/bin/env bash
# Redeploy after a change:  ./deploy.sh      (first time also: docker compose run --rm app python -m app.etl.load_data)
set -euo pipefail
cd "$(dirname "$0")"
git pull --ff-only
docker compose up -d --build
docker image prune -f >/dev/null
docker compose ps
