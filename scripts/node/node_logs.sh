#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${1:-}"
LINES="${LINES:-200}"
FOLLOW="${FOLLOW:-1}"

if [[ -z "$ENV_FILE" || "$ENV_FILE" == "-h" || "$ENV_FILE" == "--help" ]]; then
  echo "Usage:"
  echo "  bash node_logs /path/to/env.node"
  echo
  echo "Optional env:"
  echo "  LINES=300 FOLLOW=1 bash node_logs /path/to/env.node"
  echo "  LINES=300 FOLLOW=0 bash node_logs /path/to/env.node"
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

load_env

SERVICE_NAME="$(find_service_name)"
LOG_FILE="${DOCTOR_DEV_NODE_LOG_FILE:-}"
LOG_DIR="${DOCTOR_DEV_NODE_LOG_DIR:-}"

echo -e "${BOLD}Doctor Dev Node Logs${RESET}"
echo "Env:     $ENV_FILE"
echo "Service: $SERVICE_NAME"
echo "Lines:   $LINES"
echo

if [[ -z "$LOG_FILE" && -n "$LOG_DIR" ]]; then
  LOG_FILE="${LOG_DIR%/}/node.log"
fi

if [[ -n "$LOG_FILE" && -f "$LOG_FILE" ]]; then
  ok "Node log file found: $LOG_FILE"
  echo

  if [[ "$FOLLOW" == "1" ]]; then
    log "Following node log file. Press Ctrl+C to exit."
    tail -n "$LINES" -f "$LOG_FILE"
  else
    log "Showing last $LINES lines from node log file."
    tail -n "$LINES" "$LOG_FILE"
  fi

  exit 0
fi

warn "Node log file was not found from env."
echo "Tried:"
echo "  DOCTOR_DEV_NODE_LOG_FILE=${LOG_FILE:-empty}"
echo "  DOCTOR_DEV_NODE_LOG_DIR=${LOG_DIR:-empty}"
echo

if command -v systemctl >/dev/null 2>&1 && systemctl status "$SERVICE_NAME" >/dev/null 2>&1; then
  ok "Using journalctl for service: $SERVICE_NAME"
  echo

  if [[ "$FOLLOW" == "1" ]]; then
    journalctl -u "$SERVICE_NAME" -n "$LINES" -f
  else
    journalctl -u "$SERVICE_NAME" -n "$LINES" --no-pager
  fi
else
  err "No log file found and systemd service was not found."
  exit 1
fi