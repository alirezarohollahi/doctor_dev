#!/usr/bin/env bash
set -Eeuo pipefail

APP_TITLE="Doctor Dev Node Installer"
SCRIPT_VERSION="1.1.0"

YES=0
FORCE=0
NO_START=0
NO_SYSTEMD=0
NO_KILL_EXISTING=0

PROJECT_DIR="$(pwd)"
ENV_FILE=""
SERVICE_NAME="doctor-dev-node"
BIND_HOST="0.0.0.0"
API_PORT="62051"
API_KEY=""
NODE_DATA_DIR=""
NODE_LOG_DIR=""
RUN_USER=""
DEBUG_MODE="false"
PYTHON_LOG_LEVEL="INFO"
UVICORN_LOG_LEVEL="info"
INSTALL_LOG=""

if [[ -t 1 ]] && command -v tput >/dev/null 2>&1 && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  BOLD="$(tput bold)"
  DIM="$(tput dim)"
  RESET="$(tput sgr0)"
  RED="$(tput setaf 1)"
  GREEN="$(tput setaf 2)"
  YELLOW="$(tput setaf 3)"
  BLUE="$(tput setaf 4)"
  MAGENTA="$(tput setaf 5)"
  CYAN="$(tput setaf 6)"
  WHITE="$(tput setaf 7)"
else
  BOLD=""
  DIM=""
  RESET=""
  RED=""
  GREEN=""
  YELLOW=""
  BLUE=""
  MAGENTA=""
  CYAN=""
  WHITE=""
fi

usage() {
  cat <<EOF
${APP_TITLE} v${SCRIPT_VERSION}

Usage:
  bash install_node [options]

Options:
  --yes                       Use provided values/defaults and do not ask questions
  --force                     Overwrite env/service files and kill port listeners without asking
  --no-start                  Install but do not start/restart service
  --no-systemd                Do not create systemd service
  --no-kill-existing          Do not stop/kill old service/processes
  --project-dir PATH          Project directory
  --env-file PATH             Node env file path
  --service-name NAME         systemd service name
  --host HOST                 Node API bind host
  --port PORT                 Node API port
  --api-key KEY               Node API key
  --user USER                 Linux user for systemd service
  --data-dir PATH             Node data directory
  --log-dir PATH              Node log directory
  --debug true|false          DEBUG value
  --python-log-level LEVEL    PYTHON_LOG_LEVEL value
  --uvicorn-log-level LEVEL   UVICORN_LOG_LEVEL value
  --install-log PATH          Installer log file path
  -h, --help                  Show help

Full example:
  sudo bash install_node \\
    --yes \\
    --force \\
    --project-dir /home/doctor_dev \\
    --env-file /home/doctor_dev/env.node \\
    --service-name doctor-dev-node \\
    --host 0.0.0.0 \\
    --port 62051 \\
    --api-key 'CHANGE_THIS_NODE_API_KEY' \\
    --user root \\
    --data-dir /home/doctor_dev/data/node \\
    --log-dir /home/doctor_dev/logs/node \\
    --debug false \\
    --python-log-level INFO \\
    --uvicorn-log-level info
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1; shift ;;
    --force) FORCE=1; shift ;;
    --no-start) NO_START=1; shift ;;
    --no-systemd) NO_SYSTEMD=1; shift ;;
    --no-kill-existing) NO_KILL_EXISTING=1; shift ;;
    --project-dir) PROJECT_DIR="${2:-}"; shift 2 ;;
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    --service-name) SERVICE_NAME="${2:-}"; shift 2 ;;
    --host) BIND_HOST="${2:-}"; shift 2 ;;
    --port) API_PORT="${2:-}"; shift 2 ;;
    --api-key) API_KEY="${2:-}"; shift 2 ;;
    --user) RUN_USER="${2:-}"; shift 2 ;;
    --data-dir) NODE_DATA_DIR="${2:-}"; shift 2 ;;
    --log-dir) NODE_LOG_DIR="${2:-}"; shift 2 ;;
    --debug) DEBUG_MODE="${2:-}"; shift 2 ;;
    --python-log-level) PYTHON_LOG_LEVEL="${2:-}"; shift 2 ;;
    --uvicorn-log-level) UVICORN_LOG_LEVEL="${2:-}"; shift 2 ;;
    --install-log) INSTALL_LOG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "${RED}Unknown option:${RESET} $1"; usage; exit 1 ;;
  esac
done

hr() {
  printf '%b\n' "${DIM}────────────────────────────────────────────────────────────${RESET}"
}

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

banner() {
  clear 2>/dev/null || true
  printf '%b\n' "${CYAN}${BOLD}"
  printf '%s\n' "╔════════════════════════════════════════════════════════════╗"
  printf '%s\n' "║                  Doctor Dev Node Installer                ║"
  printf '%s\n' "║        stop old node • overwrite env • install service     ║"
  printf '%s\n' "╚════════════════════════════════════════════════════════════╝"
  printf '%b\n' "${RESET}"
  printf '%b\n' "${DIM}Version ${SCRIPT_VERSION}${RESET}"
  hr
}

step() {
  printf '\n%b\n' "${CYAN}${BOLD}▶ $1${RESET}"
}

ok() {
  printf '%b\n' "${GREEN}✓${RESET} $1"
}

warn() {
  printf '%b\n' "${YELLOW}⚠${RESET} $1"
}

err() {
  printf '%b\n' "${RED}✗${RESET} $1" >&2
}

die() {
  err "$1"
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

run() {
  printf '%b\n' "${BLUE}${BOLD}$${RESET} $*"
  "$@"
}

is_root() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]]
}

sudo_cmd() {
  if is_root; then
    run "$@"
  elif need_cmd sudo; then
    run sudo "$@"
  else
    die "This action needs root privileges. Re-run as root or install sudo."
  fi
}

prompt() {
  local label="$1"
  local default="$2"
  local value=""

  if [[ "$YES" -eq 1 ]]; then
    printf '%s\n' "$default"
    return
  fi

  printf '%b' "${WHITE}${label}${RESET} ${DIM}[${default}]${RESET}: "
  read -r value || true
  if [[ -z "$value" ]]; then
    value="$default"
  fi
  printf '%s\n' "$value"
}

prompt_secret() {
  local label="$1"
  local default="$2"
  local value=""

  if [[ "$YES" -eq 1 ]]; then
    printf '%s\n' "$default"
    return
  fi

  printf '%b' "${WHITE}${label}${RESET} ${DIM}[auto-generated if empty]${RESET}: "
  read -r value || true
  if [[ -z "$value" ]]; then
    value="$default"
  fi
  printf '%s\n' "$value"
}

confirm() {
  local label="$1"
  local default="${2:-yes}"
  local answer=""

  if [[ "$YES" -eq 1 || "$FORCE" -eq 1 ]]; then
    return 0
  fi

  if [[ "$default" == "yes" ]]; then
    printf '%b' "${WHITE}${label}${RESET} ${DIM}[Y/n]${RESET}: "
  else
    printf '%b' "${WHITE}${label}${RESET} ${DIM}[y/N]${RESET}: "
  fi

  read -r answer || true
  answer="${answer,,}"

  if [[ -z "$answer" ]]; then
    answer="$default"
  fi

  [[ "$answer" == "y" || "$answer" == "yes" ]]
}

abs_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$(pwd)/$path"
  fi
}

validate_port() {
  local p="$1"
  [[ "$p" =~ ^[0-9]+$ ]] || die "Invalid port: $p"
  (( p >= 1 && p <= 65535 )) || die "Port out of range 1..65535: $p"
}

generate_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

detect_default_user() {
  local owner=""
  owner="$(stat -c '%U' "$PROJECT_DIR" 2>/dev/null || true)"
  if [[ -n "$owner" && "$owner" != "UNKNOWN" ]]; then
    printf '%s\n' "$owner"
  else
    id -un
  fi
}

setup_install_log() {
  if [[ -z "$INSTALL_LOG" ]]; then
    INSTALL_LOG="/tmp/doctor_dev_install_node_$(date -u +%Y%m%d_%H%M%S).log"
  fi

  mkdir -p "$(dirname "$INSTALL_LOG")"
  touch "$INSTALL_LOG"
  chmod 600 "$INSTALL_LOG" || true

  exec > >(tee -a "$INSTALL_LOG") 2>&1

  ok "Installer log: $INSTALL_LOG"
}

install_system_packages_if_needed() {
  local missing=()

  need_cmd python3 || missing+=("python3")
  need_cmd curl || missing+=("curl")

  if ! python3 -m venv --help >/dev/null 2>&1; then
    missing+=("python3-venv")
  fi

  if [[ "${#missing[@]}" -eq 0 ]]; then
    ok "System dependencies are available."
    return
  fi

  warn "Missing system dependencies: ${missing[*]}"

  if need_cmd apt-get; then
    if confirm "Install missing packages with apt-get?" "yes"; then
      sudo_cmd apt-get update
      sudo_cmd apt-get install -y python3 python3-venv python3-pip curl
      ok "System packages installed."
    else
      die "Cannot continue without required system packages."
    fi
  else
    die "Missing dependencies and apt-get was not found. Install python3, python3-venv, python3-pip, curl manually."
  fi
}

ensure_project() {
  PROJECT_DIR="$(abs_path "$PROJECT_DIR")"

  [[ -d "$PROJECT_DIR" ]] || die "Project directory does not exist: $PROJECT_DIR"
  [[ -f "$PROJECT_DIR/main.py" ]] || die "main.py not found in project directory: $PROJECT_DIR"
  [[ -f "$PROJECT_DIR/requirements.txt" ]] || die "requirements.txt not found in project directory: $PROJECT_DIR"

  cd "$PROJECT_DIR"
  ok "Project directory: $PROJECT_DIR"
}

ensure_run_user() {
  if id "$RUN_USER" >/dev/null 2>&1; then
    ok "Service user exists: $RUN_USER"
    return
  fi

  warn "Service user does not exist: $RUN_USER"

  if confirm "Create system user '$RUN_USER'?" "yes"; then
    sudo_cmd useradd --system --home-dir "$PROJECT_DIR" --shell /usr/sbin/nologin "$RUN_USER"
    ok "Created service user: $RUN_USER"
  else
    die "Service user is required."
  fi
}

collect_pids_from_port() {
  local port="$1"
  local pids=""

  if need_cmd lsof; then
    pids="$(
      lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    )"
  fi

  if [[ -z "$pids" ]] && need_cmd fuser; then
    pids="$(
      fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' || true
    )"
  fi

  if [[ -z "$pids" ]] && need_cmd ss; then
    pids="$(
      ss -ltnp "sport = :$port" 2>/dev/null \
        | grep -oE 'pid=[0-9]+' \
        | cut -d= -f2 \
        | sort -u || true
    )"
  fi

  printf '%s\n' "$pids" | awk 'NF' | sort -u
}

collect_doctor_node_pids() {
  {
    pgrep -f "${PROJECT_DIR}/main.py.*--mode node" 2>/dev/null || true
    pgrep -f "main.py.*--mode node.*--port ${API_PORT}" 2>/dev/null || true
    pgrep -f "DOCTOR_DEV_ENV=${ENV_FILE}" 2>/dev/null || true
    pgrep -f "doctor_dev_node.server" 2>/dev/null || true
  } | awk -v self="$$" '$1 != self && $1 ~ /^[0-9]+$/ {print $1}' | sort -u
}

show_pid_details() {
  local pids="$1"
  local pid=""

  for pid in $pids; do
    if [[ -d "/proc/$pid" ]]; then
      printf '%b\n' "${YELLOW}PID ${pid}:${RESET} $(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || ps -p "$pid" -o command= 2>/dev/null || true)"
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
    ok "No processes to kill for: $reason"
    return
  fi

  warn "Processes found for ${reason}: $pids"
  show_pid_details "$pids"

  if ! confirm "Kill these processes?" "yes"; then
    die "Cannot continue while old node/port process is running."
  fi

  run kill -TERM $pids 2>/dev/null || true

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
    run kill -KILL $alive 2>/dev/null || true
  fi

  ok "Killed old processes for: $reason"
}

stop_existing_node() {
  if [[ "$NO_KILL_EXISTING" -eq 1 ]]; then
    warn "Skipping old service/process cleanup because --no-kill-existing was used."
    return
  fi

  step "Stop old node service/processes"

  if [[ "$NO_SYSTEMD" -eq 0 ]] && need_cmd systemctl; then
    if systemctl list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1 || systemctl status "$SERVICE_NAME" >/dev/null 2>&1; then
      warn "Existing systemd service detected: $SERVICE_NAME"
      sudo_cmd systemctl stop "$SERVICE_NAME" || true
      ok "Stopped service if it was running: $SERVICE_NAME"
    else
      ok "No existing systemd service detected: $SERVICE_NAME"
    fi
  fi

  local project_pids=""
  project_pids="$(collect_doctor_node_pids || true)"
  if [[ -n "$project_pids" ]]; then
    kill_pids "existing Doctor Dev node processes" $project_pids
  else
    ok "No Doctor Dev node process detected."
  fi

  local port_pids=""
  port_pids="$(collect_pids_from_port "$API_PORT" || true)"
  if [[ -n "$port_pids" ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
      kill_pids "processes listening on TCP port ${API_PORT}" $port_pids
    else
      warn "Port ${API_PORT} is already in use."
      show_pid_details "$port_pids"
      if confirm "Kill listener(s) on port ${API_PORT}?" "yes"; then
        kill_pids "processes listening on TCP port ${API_PORT}" $port_pids
      else
        die "Port ${API_PORT} is busy. Free it or choose another port."
      fi
    fi
  else
    ok "Port ${API_PORT} is free."
  fi
}

write_env_file() {
  local app_secret=""
  app_secret="$(generate_secret)"

  if [[ -f "$ENV_FILE" && "$FORCE" -ne 1 ]]; then
    if ! confirm "Env file already exists. Overwrite it?" "no"; then
      warn "Keeping existing env file: $ENV_FILE"
      return
    fi
  fi

  mkdir -p "$(dirname "$ENV_FILE")"

  umask 077
  cat > "$ENV_FILE" <<EOF
# Doctor Dev Node environment
# Generated by install_node at $(now_utc)

DOCTOR_DEV_MODE=node
APP_NAME=DoctorDevNode
APP_ENV=production
APP_SECRET=${app_secret}

NODE_HOST=${BIND_HOST}
HOST=${BIND_HOST}
API_PORT=${API_PORT}
PORT=${API_PORT}
API_KEY=${API_KEY}

DOCTOR_DEV_NODE_DATA_DIR=${NODE_DATA_DIR}
DOCTOR_DEV_NODE_ROUTING_CONFIG=${NODE_DATA_DIR}/routing-config.json
DOCTOR_DEV_NODE_LOG_DIR=${NODE_LOG_DIR}
DOCTOR_DEV_NODE_LOG_FILE=${NODE_LOG_DIR}/node.log

DEBUG=${DEBUG_MODE}
PYTHON_LOG_LEVEL=${PYTHON_LOG_LEVEL}
UVICORN_LOG_LEVEL=${UVICORN_LOG_LEVEL}

DOCTOR_DEV_FORWARD_BUFFER_SIZE=262144
DOCTOR_DEV_FORWARD_CONNECT_TIMEOUT=5
DOCTOR_DEV_FORWARD_SHUTDOWN_TIMEOUT=3
DOCTOR_DEV_FORWARD_BACKLOG=4096

DOCTOR_DEV_NODE_PEER_SYNC_INTERVAL=10
DOCTOR_DEV_NODE_PEER_SYNC_TIMEOUT=3
EOF

  chmod 600 "$ENV_FILE"
  ok "Wrote env file: $ENV_FILE"
}

setup_directories() {
  mkdir -p "$NODE_DATA_DIR" "$NODE_LOG_DIR" "$PROJECT_DIR/run" "$PROJECT_DIR/logs/install"

  local group_name
  group_name="$(id -gn "$RUN_USER" 2>/dev/null || echo "$RUN_USER")"

  sudo_cmd chown -R "$RUN_USER:$group_name" "$NODE_DATA_DIR" "$NODE_LOG_DIR" "$PROJECT_DIR/run"
  sudo_cmd chmod 750 "$NODE_DATA_DIR" "$NODE_LOG_DIR" "$PROJECT_DIR/run"

  ok "Prepared node data/log directories."
}

setup_venv() {
  local venv_dir="$PROJECT_DIR/.venv"

  if [[ -d "$venv_dir" ]]; then
    ok "Using existing venv: $venv_dir"
  else
    run python3 -m venv "$venv_dir"
    ok "Created venv: $venv_dir"
  fi

  run "$venv_dir/bin/python" -m pip install --upgrade pip setuptools wheel

  if ! "$venv_dir/bin/pip" install --no-cache-dir --only-binary=:all: -r "$PROJECT_DIR/requirements.txt"; then
    warn "Binary-only install failed. Retrying normal pip install..."
    run "$venv_dir/bin/pip" install --no-cache-dir -r "$PROJECT_DIR/requirements.txt"
  fi

  run "$venv_dir/bin/python" -m compileall -q "$PROJECT_DIR/doctor_dev_panel" "$PROJECT_DIR/doctor_dev_node" "$PROJECT_DIR/main.py"

  ok "Python environment is ready."
}

write_systemd_service() {
  local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
  local venv_python="$PROJECT_DIR/.venv/bin/python"
  local group_name
  group_name="$(id -gn "$RUN_USER" 2>/dev/null || echo "$RUN_USER")"

  if [[ "$NO_SYSTEMD" -eq 1 ]]; then
    warn "Skipping systemd service creation."
    return
  fi

  need_cmd systemctl || die "systemctl not found. Use --no-systemd if this system does not use systemd."

  if [[ -f "$service_file" && "$FORCE" -ne 1 ]]; then
    if ! confirm "Systemd service already exists. Overwrite it?" "yes"; then
      warn "Keeping existing service file: $service_file"
      return
    fi
  fi

  sudo_cmd tee "$service_file" >/dev/null <<EOF
[Unit]
Description=Doctor Dev Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=DOCTOR_DEV_ENV=${ENV_FILE}
ExecStart=${venv_python} ${PROJECT_DIR}/main.py --mode node --env ${ENV_FILE} --host ${BIND_HOST} --port ${API_PORT}
Restart=always
RestartSec=3
User=${RUN_USER}
Group=${group_name}
RuntimeDirectory=${SERVICE_NAME}
RuntimeDirectoryMode=0750
NoNewPrivileges=false

[Install]
WantedBy=multi-user.target
EOF

  sudo_cmd systemctl daemon-reload
  sudo_cmd systemctl enable "$SERVICE_NAME"

  ok "Installed/overwrote systemd service: $SERVICE_NAME"
}

start_service() {
  if [[ "$NO_SYSTEMD" -eq 1 ]]; then
    warn "No systemd service was created. Start manually with:"
    printf '%b\n' "${CYAN}${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/main.py --mode node --env ${ENV_FILE} --host ${BIND_HOST} --port ${API_PORT}${RESET}"
    return
  fi

  if [[ "$NO_START" -eq 1 ]]; then
    warn "Service start skipped."
    return
  fi

  sudo_cmd systemctl restart "$SERVICE_NAME"
  ok "Service restarted: $SERVICE_NAME"
}

health_check() {
  if [[ "$NO_START" -eq 1 ]]; then
    return
  fi

  local check_host="$BIND_HOST"
  if [[ "$check_host" == "0.0.0.0" || "$check_host" == "::" || "$check_host" == "[::]" ]]; then
    check_host="127.0.0.1"
  fi

  step "Health check"

  python3 - "$check_host" "$API_PORT" <<'PY'
import json
import sys
import time
import urllib.request

host = sys.argv[1]
port = int(sys.argv[2])
url = f"http://{host}:{port}/health"

last_error = None

for i in range(30):
    try:
        print(f"[health-check] attempt {i + 1}/30 -> {url}", flush=True)
        with urllib.request.urlopen(url, timeout=2) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            print(f"✓ Node health OK: {url}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            sys.exit(0)
    except Exception as exc:
        last_error = exc
        time.sleep(1)

print(f"✗ Health check failed: {url}")
print(f"Last error: {last_error}")
sys.exit(1)
PY
}

show_service_status() {
  if [[ "$NO_SYSTEMD" -eq 1 ]]; then
    return
  fi

  step "Service status"
  sudo_cmd systemctl status "$SERVICE_NAME" --no-pager -l || true
}

summary() {
  local check_host="$BIND_HOST"
  if [[ "$check_host" == "0.0.0.0" || "$check_host" == "::" || "$check_host" == "[::]" ]]; then
    check_host="127.0.0.1"
  fi

  hr
  printf '%b\n' "${GREEN}${BOLD}Doctor Dev Node install finished.${RESET}"
  hr
  printf '%b\n' "${WHITE}Project:${RESET}      $PROJECT_DIR"
  printf '%b\n' "${WHITE}Env file:${RESET}     $ENV_FILE"
  printf '%b\n' "${WHITE}Service:${RESET}      $SERVICE_NAME"
  printf '%b\n' "${WHITE}Bind:${RESET}         $BIND_HOST:$API_PORT"
  printf '%b\n' "${WHITE}Data dir:${RESET}     $NODE_DATA_DIR"
  printf '%b\n' "${WHITE}Log dir:${RESET}      $NODE_LOG_DIR"
  printf '%b\n' "${WHITE}Run user:${RESET}     $RUN_USER"
  printf '%b\n' "${WHITE}Install log:${RESET}  $INSTALL_LOG"
  hr

  if [[ "$NO_SYSTEMD" -eq 0 ]]; then
    printf '%b\n' "${CYAN}Useful commands:${RESET}"
    printf '%s\n' "  systemctl status ${SERVICE_NAME} --no-pager -l"
    printf '%s\n' "  journalctl -u ${SERVICE_NAME} -f"
    printf '%s\n' "  systemctl restart ${SERVICE_NAME}"
  fi

  printf '%s\n' "  curl http://${check_host}:${API_PORT}/health"
  printf '%s\n' "  curl -H 'Authorization: Bearer ${API_KEY}' http://${check_host}:${API_PORT}/runtime"
  hr
}

main() {
  banner

  step "Collect node install settings"

  PROJECT_DIR="$(prompt "Project directory" "$PROJECT_DIR")"
  PROJECT_DIR="$(abs_path "$PROJECT_DIR")"

  if [[ -z "$ENV_FILE" ]]; then
    ENV_FILE="$PROJECT_DIR/env.node"
  fi

  if [[ -z "$NODE_DATA_DIR" ]]; then
    NODE_DATA_DIR="$PROJECT_DIR/data/node"
  fi

  if [[ -z "$NODE_LOG_DIR" ]]; then
    NODE_LOG_DIR="$PROJECT_DIR/logs/node"
  fi

  if [[ -z "$RUN_USER" ]]; then
    RUN_USER="$(detect_default_user)"
  fi

  ENV_FILE="$(prompt "Node env file" "$ENV_FILE")"
  SERVICE_NAME="$(prompt "Systemd service name" "$SERVICE_NAME")"
  BIND_HOST="$(prompt "Node API bind host" "$BIND_HOST")"
  API_PORT="$(prompt "Node API port" "$API_PORT")"
  validate_port "$API_PORT"

  if [[ -z "$API_KEY" ]]; then
    API_KEY="$(generate_secret)"
  fi
  API_KEY="$(prompt_secret "Node API key" "$API_KEY")"
  [[ -n "$API_KEY" ]] || die "API key cannot be empty."

  NODE_DATA_DIR="$(prompt "Node data directory" "$NODE_DATA_DIR")"
  NODE_LOG_DIR="$(prompt "Node log directory" "$NODE_LOG_DIR")"
  RUN_USER="$(prompt "Linux service user" "$RUN_USER")"

  ENV_FILE="$(abs_path "$ENV_FILE")"
  NODE_DATA_DIR="$(abs_path "$NODE_DATA_DIR")"
  NODE_LOG_DIR="$(abs_path "$NODE_LOG_DIR")"

  setup_install_log

  hr
  printf '%b\n' "${MAGENTA}${BOLD}Install plan:${RESET}"
  printf '%b\n' "  ${WHITE}1.${RESET} Validate project"
  printf '%b\n' "  ${WHITE}2.${RESET} Stop existing systemd service if present"
  printf '%b\n' "  ${WHITE}3.${RESET} Kill old Doctor Dev node processes"
  printf '%b\n' "  ${WHITE}4.${RESET} Kill listener on selected API port if needed"
  printf '%b\n' "  ${WHITE}5.${RESET} Install/check system dependencies"
  printf '%b\n' "  ${WHITE}6.${RESET} Prepare service user and directories"
  printf '%b\n' "  ${WHITE}7.${RESET} Overwrite node env file when --force is used"
  printf '%b\n' "  ${WHITE}8.${RESET} Create/reuse Python virtual environment"
  printf '%b\n' "  ${WHITE}9.${RESET} Install requirements and compile-check code"
  printf '%b\n' "  ${WHITE}10.${RESET} Overwrite systemd service when --force is used"
  printf '%b\n' "  ${WHITE}11.${RESET} Start/restart service"
  printf '%b\n' "  ${WHITE}12.${RESET} Run /health check and show service status"
  hr

  if ! confirm "Continue with this install plan?" "yes"; then
    die "Install cancelled."
  fi

  step "Validate project"
  ensure_project

  stop_existing_node

  step "Install/check dependencies"
  install_system_packages_if_needed

  step "Prepare service user"
  ensure_run_user

  step "Prepare directories"
  setup_directories

  step "Write node env"
  write_env_file

  step "Setup Python environment"
  setup_venv

  step "Install systemd service"
  write_systemd_service

  step "Start node"
  start_service

  health_check || warn "Node service was installed, but health check failed. Check logs with: journalctl -u ${SERVICE_NAME} -f"

  show_service_status

  summary
}

main "$@"