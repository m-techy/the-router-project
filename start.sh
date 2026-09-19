#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

find_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_BIN="$(find_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.11 or newer was not found."
  echo "Install Python, then run ./start.sh again."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating lightweight local environment..."
  "$PYTHON_BIN" -m venv .venv
fi

VPY=".venv/bin/python"
DEPS_HASH="$("$PYTHON_BIN" -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("pyproject.toml").read_bytes()).hexdigest())')"
DEPS_MARKER=".venv/.router-deps-$DEPS_HASH"

if [ ! -f "$DEPS_MARKER" ]; then
  echo "Installing or updating The Router dependencies..."
  "$VPY" -m pip install --disable-pip-version-check -e .
  rm -f .venv/.router-deps-*
  : > "$DEPS_MARKER"
else
  echo "Dependencies already ready."
fi

mkdir -p data

(
  i=0
  while [ "$i" -lt 60 ]; do
    if "$VPY" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:4010/health", timeout=2)' >/dev/null 2>&1; then
      if command -v open >/dev/null 2>&1; then
        open http://localhost:4010 >/dev/null 2>&1 || true
      elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open http://localhost:4010 >/dev/null 2>&1 || true
      fi
      exit 0
    fi
    i=$((i + 1))
    sleep 1
  done
) &

echo
echo "Starting The Router in lightweight native mode..."
echo "Dashboard: http://localhost:4010"
echo "API:       http://localhost:4010/v1"
echo "Stop:      Ctrl+C"
echo "Docker:    use ./start-docker.sh instead"
echo

exec "$VPY" -m uvicorn app.main:app --host 127.0.0.1 --port 4010
