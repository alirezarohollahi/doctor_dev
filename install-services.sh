#!/usr/bin/env bash
set -euo pipefail

# Doctor Node Service Manager
# Usage examples:
#   sudo ./install-services.sh list
#   sudo ./install-services.sh install freedom-001-node
#   sudo ./install-services.sh install all
#   sudo ./install-services.sh status freedom-001-node
#   sudo ./install-services.sh logs freedom-001-node -f
#   sudo ./install-services.sh reinstall first-001-node
#   sudo ./install-services.sh uninstall freedom-001-node

SCRIPT_NAME="$(basename "$0")"
DEFAULT_PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$DEFAULT_PROJECT_DIR}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
SERVICE_PREFIX="${SERVICE_PREFIX:-doctor}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_AS_USER="${RUN_AS_USER:-}"
SKIP_DEPS=0
NO_ENABLE=0
NO_START=0
TAIL_LINES=200
FOLLOW_LOGS=0

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue() { printf '\033[34m%s\033[0m\n' "$*"; }

usage() {
  cat <<USAGE
Doctor Node Service Manager

Usage:
  sudo ./$SCRIPT_NAME <command> [node|all] [options]

Commands:
  list                         Show detected nodes under DocNodes/*/configs/*.env
  install <node|all>           Create venv, install deps, write systemd unit, enable/start service
  reinstall <node|all>         Stop/remove old unit, install again, enable/start service
  uninstall <node|all>         Stop, disable, and remove systemd unit; project files are kept
  status <node|all>            Show systemd status
  logs <node> [-f] [-n N]       Show journal logs for one node
  start <node|all>             Start service
  stop <node|all>              Stop service
  restart <node|all>           Restart service
  enable <node|all>            Enable service at boot
  disable <node|all>           Disable service at boot
  unit <node>                  Print generated systemd unit without installing
  help                         Show this help

Options:
  --project-dir PATH           Project root. Default: directory of this script
  --user USER                  Run service as this Linux user. Default: root/systemd default
  --skip-deps                  Do not create/update .venv or pip install requirements.txt
  --no-enable                  Install but do not enable at boot
  --no-start                   Install but do not start/restart now
  -n, --lines N                Number of log lines for logs command. Default: 200
  -f, --follow                 Follow logs

Environment overrides:
  PROJECT_DIR=/path/to/project
  SYSTEMD_DIR=/etc/systemd/system
  SERVICE_PREFIX=doctor
  PYTHON_BIN=python3
  RUN_AS_USER=someuser

Examples:
  sudo ./$SCRIPT_NAME install freedom-001-node
  sudo ./$SCRIPT_NAME install first-001-node --project-dir /home/doctor_dev
  sudo ./$SCRIPT_NAME status all
  sudo ./$SCRIPT_NAME logs freedom-001-node -f
  sudo ./$SCRIPT_NAME reinstall all
  sudo ./$SCRIPT_NAME uninstall first-001-node
USAGE
}

need_root_for_systemd() {
  if [[ "${EUID}" -ne 0 ]]; then
    red "This command changes systemd units. Run it with sudo."
    exit 1
  fi
}

abs_path() {
  local p="$1"
  if [[ "$p" = /* ]]; then
    printf '%s\n' "$p"
  else
    printf '%s/%s\n' "$PROJECT_DIR" "$p"
  fi
}

sanitize_service_name() {
  local node="$1"
  printf '%s' "${SERVICE_PREFIX}-${node}" | tr -c 'A-Za-z0-9_.@-' '-'
}

service_name() {
  local node="$1"
  printf '%s.service\n' "$(sanitize_service_name "$node")"
}

unit_path() {
  local node="$1"
  printf '%s/%s\n' "$SYSTEMD_DIR" "$(service_name "$node")"
}

node_env_path() {
  local node="$1"
  printf '%s/DocNodes/%s/configs/%s.env\n' "$PROJECT_DIR" "$node" "$node"
}

read_env_value() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 1
  local line value
  line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1
  value="${line#*=}"
  value="${value%$'\r'}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s\n' "$value"
}

config_path_for_node() {
  local node="$1" env_file cfg
  env_file="$(node_env_path "$node")"
  cfg="$(read_env_value "$env_file" DOCTOR_DEV_CONFIG_PATH || true)"
  [[ -n "$cfg" ]] || cfg="$(read_env_value "$env_file" START_CONFIG || true)"
  [[ -n "$cfg" ]] || cfg="DocNodes/$node/configs/$node.json"
  abs_path "$cfg"
}

runtime_path_for_node() {
  local node="$1" env_file rt
  env_file="$(node_env_path "$node")"
  rt="$(read_env_value "$env_file" DOCTOR_DEV_RUNTIME_PATH || true)"
  [[ -n "$rt" ]] || rt="$(read_env_value "$env_file" START_RUNTIME || true)"
  [[ -n "$rt" ]] || rt="DocNodes/$node/configs/$node.runtime.json"
  abs_path "$rt"
}

validate_project() {
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
  [[ -f "$PROJECT_DIR/main.py" ]] || { red "main.py not found in PROJECT_DIR: $PROJECT_DIR"; exit 1; }
  [[ -d "$PROJECT_DIR/DocNodes" ]] || { red "DocNodes directory not found in PROJECT_DIR: $PROJECT_DIR"; exit 1; }
}

detect_nodes() {
  validate_project
  local env_file node
  shopt -s nullglob
  for env_file in "$PROJECT_DIR"/DocNodes/*/configs/*.env; do
    node="$(basename "$(dirname "$(dirname "$env_file")")")"
    if [[ "$(basename "$env_file")" == "$node.env" ]]; then
      printf '%s\n' "$node"
    fi
  done | sort -u
  shopt -u nullglob
}

ensure_node_exists() {
  local node="$1" env_file cfg
  env_file="$(node_env_path "$node")"
  [[ -f "$env_file" ]] || { red "Env file not found for node '$node': $env_file"; exit 1; }
  cfg="$(config_path_for_node "$node")"
  [[ -f "$cfg" ]] || { red "Config file not found for node '$node': $cfg"; exit 1; }
}

expand_target_nodes() {
  local target="${1:-}"
  [[ -n "$target" ]] || { red "Node name is required. Use 'list' to see nodes."; exit 1; }
  if [[ "$target" == "all" ]]; then
    detect_nodes
  else
    ensure_node_exists "$target"
    printf '%s\n' "$target"
  fi
}

install_deps() {
  [[ "$SKIP_DEPS" -eq 0 ]] || return 0
  validate_project
  if [[ ! -d "$PROJECT_DIR/.venv" ]]; then
    blue "Creating virtualenv: $PROJECT_DIR/.venv"
    "$PYTHON_BIN" -m venv "$PROJECT_DIR/.venv" || {
      red "Failed to create venv. Install python3-venv first, for example: sudo apt install python3-venv"
      exit 1
    }
  fi
  blue "Upgrading pip and installing requirements"
  "$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
  if [[ -f "$PROJECT_DIR/requirements.txt" ]]; then
    "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
  else
    yellow "requirements.txt not found; skipping pip install"
  fi
}

prepare_dirs() {
  mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/run"
  if [[ -n "$RUN_AS_USER" ]]; then
    if id "$RUN_AS_USER" >/dev/null 2>&1; then
      chown -R "$RUN_AS_USER":"$RUN_AS_USER" "$PROJECT_DIR/logs" "$PROJECT_DIR/run" || true
    else
      red "User '$RUN_AS_USER' does not exist."
      exit 1
    fi
  fi
}

generate_unit() {
  local node="$1" env_file svc cfg rt user_block caps_block
  env_file="$(node_env_path "$node")"
  svc="$(sanitize_service_name "$node")"
  cfg="$(config_path_for_node "$node")"
  rt="$(runtime_path_for_node "$node")"

  user_block=""
  if [[ -n "$RUN_AS_USER" ]]; then
    user_block="User=$RUN_AS_USER
Group=$RUN_AS_USER"
  fi

  # CAP_NET_BIND_SERVICE lets non-root services bind 80/443 if the node config needs it.
  caps_block="CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=true"

  cat <<UNIT
[Unit]
Description=Doctor Admin Node - $node
Documentation=file:$PROJECT_DIR
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
$user_block
Environment=PYTHONUNBUFFERED=1
Environment=UVICORN_LOG_LEVEL=info
EnvironmentFile=$env_file
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/main.py --env $env_file --config $cfg --runtime $rt
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30
LimitNOFILE=1048576
$caps_block

[Install]
WantedBy=multi-user.target
UNIT
}

validate_unit_node() {
  local node="$1"
  ensure_node_exists "$node"
  [[ -x "$PROJECT_DIR/.venv/bin/python" ]] || { red "Venv python not found: $PROJECT_DIR/.venv/bin/python"; exit 1; }
}

write_unit() {
  local node="$1" path
  path="$(unit_path "$node")"
  validate_unit_node "$node"
  generate_unit "$node" > "$path"
  chmod 644 "$path"
  green "Wrote $path"
}

systemctl_safe() {
  systemctl "$@"
}

install_node() {
  local node="$1" svc
  svc="$(service_name "$node")"
  write_unit "$node"
  systemctl_safe daemon-reload
  if [[ "$NO_ENABLE" -eq 0 ]]; then
    systemctl_safe enable "$svc"
  fi
  if [[ "$NO_START" -eq 0 ]]; then
    systemctl_safe restart "$svc"
  fi
  green "Installed $svc for node '$node'"
  systemctl_safe --no-pager --full status "$svc" || true
}

uninstall_node() {
  local node="$1" svc path
  svc="$(service_name "$node")"
  path="$(unit_path "$node")"
  systemctl_safe stop "$svc" >/dev/null 2>&1 || true
  systemctl_safe disable "$svc" >/dev/null 2>&1 || true
  rm -f "$path"
  systemctl_safe daemon-reload
  systemctl_safe reset-failed "$svc" >/dev/null 2>&1 || true
  green "Uninstalled $svc (project files kept)"
}

print_list() {
  local node env cfg rt svc active enabled
  printf '%-24s %-30s %-9s %-9s %s\n' "NODE" "SERVICE" "ACTIVE" "ENABLED" "ENV"
  printf '%-24s %-30s %-9s %-9s %s\n' "----" "-------" "------" "-------" "---"
  while IFS= read -r node; do
    [[ -n "$node" ]] || continue
    env="$(node_env_path "$node")"
    cfg="$(config_path_for_node "$node")"
    rt="$(runtime_path_for_node "$node")"
    svc="$(service_name "$node")"
    active="$(systemctl is-active "$svc" 2>/dev/null || true)"
    enabled="$(systemctl is-enabled "$svc" 2>/dev/null || true)"
    printf '%-24s %-30s %-9s %-9s %s\n' "$node" "$svc" "${active:-unknown}" "${enabled:-unknown}" "$env"
    printf '  config:  %s\n' "$cfg"
    printf '  runtime: %s\n' "$rt"
  done < <(detect_nodes)
}

run_for_nodes() {
  local command="$1" target="$2" node svc
  while IFS= read -r node; do
    [[ -n "$node" ]] || continue
    svc="$(service_name "$node")"
    case "$command" in
      install) install_node "$node" ;;
      reinstall) uninstall_node "$node"; install_node "$node" ;;
      uninstall) uninstall_node "$node" ;;
      status) systemctl_safe --no-pager --full status "$svc" || true ;;
      start) systemctl_safe start "$svc" ;;
      stop) systemctl_safe stop "$svc" ;;
      restart) systemctl_safe restart "$svc" ;;
      enable) systemctl_safe enable "$svc" ;;
      disable) systemctl_safe disable "$svc" ;;
      *) red "Unknown node command: $command"; exit 1 ;;
    esac
  done < <(expand_target_nodes "$target")
}

show_logs() {
  local node="$1" svc args
  ensure_node_exists "$node"
  svc="$(service_name "$node")"
  args=(-u "$svc" -n "$TAIL_LINES" --no-pager)
  if [[ "$FOLLOW_LOGS" -eq 1 ]]; then
    args=(-u "$svc" -n "$TAIL_LINES" -f)
  fi
  journalctl "${args[@]}"
}

COMMAND="${1:-help}"
shift || true
TARGET=""

# Keep first non-option argument as target node/all.
if [[ $# -gt 0 && "${1:-}" != --* && "${1:-}" != -* ]]; then
  TARGET="$1"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="${2:?--project-dir requires a path}"; shift 2 ;;
    --user)
      RUN_AS_USER="${2:?--user requires a username}"; shift 2 ;;
    --skip-deps)
      SKIP_DEPS=1; shift ;;
    --no-enable)
      NO_ENABLE=1; shift ;;
    --no-start)
      NO_START=1; shift ;;
    -n|--lines)
      TAIL_LINES="${2:?--lines requires a number}"; shift 2 ;;
    -f|--follow)
      FOLLOW_LOGS=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      red "Unknown option: $1"; usage; exit 1 ;;
  esac
done

case "$COMMAND" in
  help|-h|--help)
    usage ;;
  list)
    print_list ;;
  unit)
    [[ -n "$TARGET" ]] || { red "Node is required for unit command."; exit 1; }
    validate_project
    ensure_node_exists "$TARGET"
    generate_unit "$TARGET" ;;
  install|reinstall)
    need_root_for_systemd
    validate_project
    install_deps
    prepare_dirs
    run_for_nodes "$COMMAND" "$TARGET" ;;
  uninstall|status|start|stop|restart|enable|disable)
    need_root_for_systemd
    validate_project
    run_for_nodes "$COMMAND" "$TARGET" ;;
  logs)
    need_root_for_systemd
    validate_project
    [[ -n "$TARGET" && "$TARGET" != "all" ]] || { red "logs command needs exactly one node, not all."; exit 1; }
    show_logs "$TARGET" ;;
  *)
    red "Unknown command: $COMMAND"
    usage
    exit 1 ;;
esac
