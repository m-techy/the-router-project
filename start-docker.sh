#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found."
  echo "Install Docker Desktop/Engine, start it, then run ./start-docker.sh again."
  exit 1
fi

echo "Starting The Router with Docker..."
docker compose up -d --build

echo "Waiting for http://localhost:4010 ..."
i=0
until curl -fsS http://localhost:4010/health >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "The container started, but the router did not become healthy."
    echo "Run: docker compose logs router"
    exit 1
  fi
  sleep 1
done

if command -v open >/dev/null 2>&1; then
  open http://localhost:4010 >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://localhost:4010 >/dev/null 2>&1 || true
fi

echo
echo "The Router is ready in Docker mode."
echo "Dashboard: http://localhost:4010"
echo "API:       http://localhost:4010/v1"
echo "Stop:      docker compose down"
echo "Native:    use ./start.sh instead"
