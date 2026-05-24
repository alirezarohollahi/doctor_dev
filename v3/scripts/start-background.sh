#!/usr/bin/env bash
set -euo pipefail

NODE_NAME="${1:-}"
if [ -z "$NODE_NAME" ]; then
  echo "Usage: ./scripts/start-background.sh iran-node|gateway-node|forigen-node"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p logs run

case "$NODE_NAME" in
  iran-node)
    ENV_FILE="configs/iran-node.env"
    ;;
  gateway-node)
    ENV_FILE="configs/gateway-node.env"
    ;;
  forigen-node)
    ENV_FILE="configs/forigen-node.env"
    ;;
  *)
    echo "Unknown node: $NODE_NAME"
    echo "Usage: ./scripts/start-background.sh iran-node|gateway-node|forigen-node"
    exit 1
    ;;
esac

PID_FILE="run/${NODE_NAME}.pid"
LOG_FILE="logs/${NODE_NAME}.out"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "$NODE_NAME is already running with PID $(cat "$PID_FILE")"
  exit 0
fi

nohup doctor-dev --env "$ENV_FILE" > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "$NODE_NAME started"
echo "PID: $(cat "$PID_FILE")"
echo "Log: $LOG_FILE"
