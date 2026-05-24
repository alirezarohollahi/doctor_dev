#!/usr/bin/env bash
set -euo pipefail

NODE_NAME="${1:-}"
if [ -z "$NODE_NAME" ]; then
  echo "Usage: ./scripts/stop-background.sh iran-node|gateway-node|forigen-node"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PID_FILE="run/${NODE_NAME}.pid"
if [ ! -f "$PID_FILE" ]; then
  echo "No PID file found for $NODE_NAME"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped $NODE_NAME with PID $PID"
else
  echo "$NODE_NAME was not running"
fi
rm -f "$PID_FILE"
