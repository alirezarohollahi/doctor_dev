
#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-9098}"
API_KEY="${API_KEY:-11111111-1111-1111-1111-111111111111}"
TMP_DIR="${TMP_DIR:-/tmp/doctor-dev-port-test}"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR/data" "$TMP_DIR/logs"
cat > "$TMP_DIR/node.env" <<ENV
DOCTOR_DEV_MODE=node
API_KEY=$API_KEY
NODE_HOST=127.0.0.1
API_PORT=62051
DOCTOR_DEV_NODE_DATA_DIR=$TMP_DIR/data
DOCTOR_DEV_NODE_ROUTING_CONFIG=$TMP_DIR/data/routing-config.json
DOCTOR_DEV_NODE_LOG_DIR=$TMP_DIR/logs
DOCTOR_DEV_NODE_LOG_FILE=$TMP_DIR/logs/node.log
PYTHON_LOG_LEVEL=INFO
UVICORN_LOG_LEVEL=warning
ENV
cd "$ROOT_DIR"
python main.py --mode node --env "$TMP_DIR/node.env" --host 127.0.0.1 --port "$PORT" > "$TMP_DIR/stdout.log" 2>&1 &
PID=$!
cleanup(){ kill "$PID" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" > "$TMP_DIR/health.json" 2>/dev/null; then
    break
  fi
  sleep 0.2
done
curl -fsS -H "Authorization: Bearer $API_KEY" "http://127.0.0.1:$PORT/runtime" > "$TMP_DIR/runtime.json"
python - "$PORT" "$TMP_DIR/health.json" "$TMP_DIR/runtime.json" <<'PY'
import json, sys
expected = int(sys.argv[1])
health = json.load(open(sys.argv[2]))
runtime = json.load(open(sys.argv[3]))
for label, payload in [("health", health), ("runtime", runtime)]:
    api = payload.get("api") or {}
    got = int(api.get("port") or api.get("api_port") or 0)
    if got != expected:
        raise SystemExit(f"{label} reported port {got}, expected {expected}: {payload}")
print(f"[PASS] health/runtime report actual bound API port {expected}")
PY



