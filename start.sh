#!/usr/bin/env sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found."
  echo "Install Docker Desktop/Engine, start it, then run ./start.sh again."
  exit 1
fi

echo "Starting The Router..."
docker compose up -d --build

echo "Waiting for http://localhost:4010 ..."
i=0
until curl -fsS http://localhost:4010/health >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "The Router container started, but the web UI did not become healthy."
    echo "Run: docker compose logs router"
    exit 1
  fi
  sleep 1
done

echo "The Router is ready."
echo "Dashboard: http://localhost:4010"
echo "OpenAI API: http://localhost:4010/v1"

if command -v open >/dev/null 2>&1; then
  open http://localhost:4010 >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://localhost:4010 >/dev/null 2>&1 || true
fi

echo "To stop later: docker compose down"
