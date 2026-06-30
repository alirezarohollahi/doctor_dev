#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${1:-}"

if [[ -z "$ENV_FILE" || "$ENV_FILE" == "-h" || "$ENV_FILE" == "--help" ]]; then
  echo "Usage:"
  echo "  bash node_status /path/to/env.node"
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

host_for_local_check() {
  local h="${NODE_HOST:-${HOST:-127.0.0.1}}"
  if [[ "$h" == "0.0.0.0" || "$h" == "::" || "$h" == "[::]" || -z "$h" ]]; then
    h="127.0.0.1"
  fi
  echo "$h"
}

json_pretty() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool 2>/dev/null || cat
  else
    cat
  fi
}

load_env

SERVICE_NAME="$(find_service_name)"
CHECK_HOST="$(host_for_local_check)"
API_PORT="${API_PORT:-${PORT:-62051}}"
API_KEY="${API_KEY:-}"
HEALTH_URL="http://${CHECK_HOST}:${API_PORT}/health"
STATUS_URL="http://${CHECK_HOST}:${API_PORT}/status"
RUNTIME_URL="http://${CHECK_HOST}:${API_PORT}/runtime"

echo -e "${BOLD}Doctor Dev Node Status${RESET}"
echo "Env:       $ENV_FILE"
echo "Service:   $SERVICE_NAME"
echo "Host:      $CHECK_HOST"
echo "API port:  $API_PORT"
echo

log "Systemd status"
if command -v systemctl >/dev/null 2>&1; then
  systemctl status "$SERVICE_NAME" --no-pager -l || true
else
  warn "systemctl not found."
fi

echo
log "Listening port check"
if command -v ss >/dev/null 2>&1; then
  ss -ltnp "sport = :${API_PORT}" || true
elif command -v lsof >/dev/null 2>&1; then
  lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN || true
elif command -v netstat >/dev/null 2>&1; then
  netstat -ltnp 2>/dev/null | grep ":${API_PORT} " || true
else
  warn "No ss/lsof/netstat found."
fi

echo
log "Health check: $HEALTH_URL"
if curl -fsS --max-time 5 "$HEALTH_URL" | json_pretty; then
  echo
  ok "Health endpoint is OK."
else
  echo
  err "Health endpoint failed."
fi

if [[ -n "$API_KEY" ]]; then
  echo
  log "Authenticated status: $STATUS_URL"
  if curl -fsS --max-time 5 -H "Authorization: Bearer ${API_KEY}" "$STATUS_URL" | json_pretty; then
    echo
    ok "Authenticated status endpoint is OK."
  else
    echo
    err "Authenticated status endpoint failed."
  fi

  echo
  log "Runtime export: $RUNTIME_URL"
  if curl -fsS --max-time 5 -H "Authorization: Bearer ${API_KEY}" "$RUNTIME_URL" | json_pretty; then
    echo
    ok "Runtime endpoint is OK."
  else
    echo
    err "Runtime endpoint failed."
  fi
else
  warn "API_KEY is empty in env, skipping authenticated /status and /runtime checks."
fi