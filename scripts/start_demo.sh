#!/usr/bin/env bash
# One command for the demo: build the UI and serve UI + API on one port.
#   scripts/start_demo.sh            # Gemini on (uses quota)
#   scripts/start_demo.sh --offline  # no AI calls: template explanations, offline chat
#   scripts/start_demo.sh --lan      # also reachable from other devices on the network
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
OFFLINE=0; HOST=127.0.0.1; PORT=8000
for arg in "$@"; do
  case "$arg" in
    --offline) OFFLINE=1 ;;
    --lan) HOST=0.0.0.0 ;;
    --port=*) PORT="${arg#*=}" ;;
    *) echo "unknown option $arg"; exit 2 ;;
  esac
done
if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "port $PORT is busy (another DataFix running?). Stop it or use --port=8001"; exit 1
fi
echo "building the UI..."
(cd frontend && npm run build --silent >/dev/null)
echo "DataFix on http://localhost:$PORT  (offline=$OFFLINE)"
cd backend
DATAFIX_OFFLINE=$OFFLINE exec uv run uvicorn api.main:app --host "$HOST" --port "$PORT"
