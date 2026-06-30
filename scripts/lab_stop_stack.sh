
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -d run/lab ]]; then
  echo "No run/lab directory."
  exit 0
fi
for pidfile in run/lab/*.pid; do
  [[ -e "$pidfile" ]] || continue
  name="$(basename "$pidfile" .pid)"
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "[STOP] $name pid=$pid"
    kill "$pid" || true
  else
    echo "[GONE] $name pid=$pid"
  fi
  rm -f "$pidfile"
done



