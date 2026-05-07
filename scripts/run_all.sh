#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p results
rm -f results/summary.csv

STRATEGIES=("cache_aside" "write_through" "write_back")

echo "==> postgres + redis"
docker compose up -d postgres redis

for strat in "${STRATEGIES[@]}"; do
  echo
  echo "================================================================"
  echo "  STRATEGY: ${strat}"
  echo "================================================================"

  CACHE_STRATEGY="${strat}" docker compose up -d --force-recreate app

  echo "==> waiting app healthy..."
  for _ in $(seq 1 60); do
    status=$(docker inspect -f '{{.State.Health.Status}}' p3-app 2>/dev/null || echo starting)
    if [ "${status}" = "healthy" ]; then break; fi
    sleep 1
  done
  if [ "${status}" != "healthy" ]; then
    echo "app did not become healthy"; docker compose logs app | tail -50; exit 1
  fi

  CACHE_STRATEGY="${strat}" docker compose run --rm loadgen --strategy "${strat}"
done

echo
echo "==> done. results/summary.csv:"
column -s, -t < results/summary.csv | sed -e 's/^/  /'
