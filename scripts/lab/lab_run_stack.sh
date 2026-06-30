
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON_BIN:-./.venv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="python3"; fi
mkdir -p run/lab logs/lab/panel logs/lab/node-a logs/lab/node-b data/lab/panel data/lab/node-a data/lab/node-b

start_one() {
  local name="$1"; shift
  local log="logs/lab/${name}.stdout.log"
  local pidfile="run/lab/${name}.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[SKIP] $name already running pid=$(cat "$pidfile")"
    return
  fi
  echo "[START] $name -> $log"
  nohup "$@" > "$log" 2>&1 &
  echo $! > "$pidfile"
}

start_one panel "$PY" main.py --mode panel --env env.examples/lab-panel.env --host 0.0.0.0 --port 9000
start_one node-a "$PY" main.py --mode node --env env.examples/lab-node-a.env --host 127.0.0.1 --port 9001
start_one node-b "$PY" main.py --mode node --env env.examples/lab-node-b.env --host 127.0.0.1 --port 9002

sleep 2

echo
echo "PIDs:"
for f in run/lab/*.pid; do echo "  $(basename "$f" .pid): $(cat "$f")"; done

echo
echo "Health checks:"
for port in 9000 9001 9002; do
  if command -v curl >/dev/null 2>&1; then
    echo "--- :$port"
    curl -fsS "http://127.0.0.1:${port}/health" || true
    echo
  fi
done

echo
echo "Panel: http://SERVER_IP:9000"
echo "Node A API: http://127.0.0.1:9001"
echo "Node B API: http://127.0.0.1:9002"
echo "Logs: tail -f logs/lab/*.stdout.log logs/lab/*/*.log"



