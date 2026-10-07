#!/usr/bin/env bash
# One-shot demo server. Usage: ./run.sh [vue|react] [--dev]
set -euo pipefail

DEMO="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DEMO/../.." && pwd)"
WEB="${1:-vue}"
DEV=0
if [ "${2:-}" = "--dev" ] || [ "${1:-}" = "--dev" ]; then
  DEV=1
  if [ "${1:-}" = "--dev" ]; then
    WEB="${2:-vue}"
  fi
fi
if [ "$WEB" != "vue" ] && [ "$WEB" != "react" ]; then
  echo "WEB must be vue or react, got: $WEB" >&2
  exit 1
fi

VENV="$DEMO/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -U pip
fi
"$VENV/bin/pip" install -e "${ROOT}[captcha]" "uvicorn[standard]"

if [ "$DEV" -eq 0 ]; then
  if [ -f "$ROOT/packages/account-ui-vue/package.json" ]; then
    (cd "$ROOT/packages/account-ui-vue" && npm ci)
  fi
  if [ -f "$ROOT/packages/account-ui-react/package.json" ]; then
    (cd "$ROOT/packages/account-ui-react" && npm ci)
  fi
  if [ -f "$DEMO/web-$WEB/package.json" ]; then
    (cd "$DEMO/web-$WEB" && npm ci && npm run build)
  else
    echo "skip frontend build: $DEMO/web-$WEB is not present yet"
  fi
else
  echo "dev mode: start Vite in another terminal (proxy /api -> http://127.0.0.1:8000)"
  echo "  cd $DEMO/web-$WEB && npm install && npm run dev"
fi

cd "$DEMO"
export DEMO_WEB="$WEB"
RELOAD=()
[ "$DEV" -eq 1 ] && RELOAD=(--reload)
exec "$VENV/bin/uvicorn" server.app:create_app --factory --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" "${RELOAD[@]}"
