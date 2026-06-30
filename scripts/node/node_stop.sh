#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${1:-}"
FORCE="${FORCE:-1}"

if [[ -z "$ENV_FILE" || "$ENV_FILE" == "-h" || "$ENV_FILE" == "--help" ]]; then
  echo "Usage:"
  echo "  bash node_stop /path/to/env.node"
  echo
  echo "Optional env:"
  echo "  FORCE=1 bash node_stop /path/to/env.node"
  echo "  FORCE=0 bash node_stop /path/to/env.node"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

ENV_FILE="$(readlink -f "$ENV_FILE")"

if [[ -t 1 ]] && command -v tput >/dev/null 2>&1; then
  BOLD="$(tput bold)"
  RESET="$(tput sgr0)"
  RED="$(tput setaf 1)"
  GREEN="$(tput setaf 2)"
  YELLOW="$(tput setaf 3)"
  CYAN="$(tput setaf 6)"
  DIM="$(tput dim)"
else
  BOLD=""; RESET=""; RED=""; GREEN=""; YELLOW=""; CYAN=""; DIM=""
fi

log() { echo -e "${CYAN}${BOLD}▶${RESET} $*"; }
ok() { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
err() { echo -e "${RED}✗${RESET} $*" >&2; }

run_root() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    err "Root permission required. Run with sudo."
    exit 1
  fi
}

load_env() {
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
}

find_service_name() {
  if [[ -n "${DOCTOR_DEV_SERVICE_NAME:-}" ]]; then
    echo "$DOCTOR_DEV_SERVICE_NAME"
    return 0
  fi

  local unit=""
  unit="$(
    grep -Rsl \
      -e "DOCTOR_DEV_ENV=${ENV_FILE}" \
      -e "--env ${ENV_FILE}" \
      /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system 2>/dev/null \
      | head -n 1 || true
  )"

  if [[ -n "$unit" ]]; then
    basename "$unit" .service
    return 0
  fi

  echo "doctor-dev-node"
}

collect_pids_from_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  fi

  if [[ -z "$pids" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' || true)"
  fi

  if [[ -z "$pids" ]] && command -v ss >/dev/null 2>&1; then
    pids="$(
      ss -ltnp "sport = :$port" 2>/dev/null \
        | grep -oE 'pid=[0-9]+' \
        | cut -d= -f2 \
        | sort -u || true
    )"
  fi

  printf '%s\n' "$pids" | awk 'NF' | sort -u
}

collect_env_pids() {
  {
    pgrep -f "main.py.*--mode node.*--env ${ENV_FILE}" 2>/dev/null || true
    pgrep -f "main.py.*--env ${ENV_FILE}.*--mode node" 2>/dev/null || true
    pgrep -f "DOCTOR_DEV_ENV=${ENV_FILE}" 2>/dev/null || true
  } | awk -v self="$$" '$1 != self && $1 ~ /^[0-9]+$/ {print $1}' | sort -u
}

show_pid_details() {
  local pids="$1"
  local pid=""

  for pid in $pids; do
    if [[ -d "/proc/$pid" ]]; then
      echo -e "${YELLOW}PID ${pid}:${RESET} $(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || ps -p "$pid" -o command= 2>/dev/null || true)"
    else
      ps -p "$pid" -o pid=,ppid=,user=,command= 2>/dev/null || true
    fi
  done
}

kill_pids() {
  local reason="$1"
  shift
  local pids="$*"
  local alive=""
  local pid=""

  pids="$(printf '%s\n' $pids | awk '$1 ~ /^[0-9]+$/ {print $1}' | sort -u | tr '\n' ' ')"

  if [[ -z "$pids" ]]; then
    ok "No processes found for: $reason"
    return
  fi

  warn "Processes found for ${reason}: $pids"
  show_pid_details "$pids"

  if [[ "$FORCE" != "1" ]]; then
    read -r -p "Kill these processes? [y/N]: " answer
    answer="${answer,,}"
    [[ "$answer" == "y" || "$answer" == "yes" ]] || {
      err "Stop cancelled."
      exit 1
    }
  fi

  kill -TERM $pids 2>/dev/null || true

  for _ in $(seq 1 10); do
    alive=""
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        alive="$alive $pid"
      fi
    done
    [[ -z "$alive" ]] && break
    sleep 1
  done

  if [[ -n "$alive" ]]; then
    warn "Some processes survived TERM, sending KILL:$alive"
    kill -KILL $alive 2>/dev/null || true
  fi

  ok "Killed processes for: $reason"
}

load_env

SERVICE_NAME="$(find_service_name)"
API_PORT="${API_PORT:-${PORT:-62051}}"

echo -e "${BOLD}Doctor Dev Node Stop${RESET}"
echo "Env:      $ENV_FILE"
echo "Service:  $SERVICE_NAME"
echo "API port: $API_PORT"
echo

log "Stopping systemd service"
if command -v systemctl >/dev/null 2>&1 && systemctl status "$SERVICE_NAME" >/dev/null 2>&1; then
  run_root systemctl stop "$SERVICE_NAME" || true
  ok "Service stopped: $SERVICE_NAME"
else
  warn "Systemd service not found or not active: $SERVICE_NAME"
fi

echo
log "Killing processes started with this env"
ENV_PIDS="$(collect_env_pids || true)"
kill_pids "Doctor Dev node processes using env ${ENV_FILE}" $ENV_PIDS

echo
log "Checking selected API port"
PORT_PIDS="$(collect_pids_from_port "$API_PORT" || true)"
kill_pids "listeners on TCP port ${API_PORT}" $PORT_PIDS

echo
log "Final port check"
if command -v ss >/dev/null 2>&1; then
  if ss -ltnp "sport = :${API_PORT}" 2>/dev/null | grep -q ":${API_PORT}"; then
    err "Port ${API_PORT} is still busy."
    ss -ltnp "sport = :${API_PORT}" || true
    exit 1
  fi
elif command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    err "Port ${API_PORT} is still busy."
    lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN || true
    exit 1
  fi
fi

ok "Node stopped and port ${API_PORT} is free."