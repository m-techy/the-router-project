#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${ROUTER_REPO_URL:-https://github.com/m-techy/the-router-project.git}"
BRANCH="${ROUTER_INSTALL_BRANCH:-main}"
INSTALL_DIR="${ROUTER_INSTALL_DIR:-$HOME/.the-router}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "The Router installer needs '$1'." >&2
    exit 1
  }
}

need git
need python3

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("The Router needs Python 3.11 or newer.")
PY

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Updating The Router in $INSTALL_DIR"
  git -C "$INSTALL_DIR" fetch --prune origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
elif [ -e "$INSTALL_DIR" ]; then
  echo "Install path exists but is not a Router git checkout: $INSTALL_DIR" >&2
  exit 1
else
  echo "Installing The Router into $INSTALL_DIR"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

chmod +x "$INSTALL_DIR/start.sh" "$INSTALL_DIR/start-docker.sh" 2>/dev/null || true

echo
echo "The Router is installed at: $INSTALL_DIR"
echo "Dashboard: http://localhost:4010"
echo

if [ "${ROUTER_INSTALL_NO_START:-0}" = "1" ]; then
  echo "Start later with: $INSTALL_DIR/start.sh"
  exit 0
fi

exec "$INSTALL_DIR/start.sh"
