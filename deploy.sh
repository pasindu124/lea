#!/usr/bin/env bash
# Redeploy after a change:  ./deploy.sh
# Loads any dataset whose table is still empty (first deploy, or new data such as the MMEL), from ./data.
# Files that are not in git (the AMM SGML) must be copied to ./data on this machine first.
# Force a full reload:  docker compose run --rm app python -m app.etl.load_data
set -euo pipefail
cd "$(dirname "$0")"
git pull --ff-only
docker compose up -d --build
docker compose run --rm app python -m app.etl.load_data --if-empty \
  || echo "WARNING: data load failed; the app is running with the data it already had."
docker image prune -f >/dev/null
docker compose ps
