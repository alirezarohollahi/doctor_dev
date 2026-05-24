#!/usr/bin/env bash
set -euo pipefail

NODE_NAME="${1:-}"
if [ -z "$NODE_NAME" ]; then
  echo "Usage: ./scripts/status-background.sh iran-node|gateway-node|forigen-node"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PID_FILE="run/${NODE_NAME}.pid"
if [ ! -f "$PID_FILE" ]; then
  echo "$NODE_NAME is not running"
  exit 1
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  echo "$NODE_NAME is running with PID $PID"
else
  echo "$NODE_NAME is not running, but PID file exists"
  exit 1
fi
