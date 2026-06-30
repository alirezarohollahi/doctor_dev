
#!/usr/bin/env bash
set -Eeuo pipefail

# Doctor Dev installer / updater / remover.
# Remote usage:
#   curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
#     && sudo bash /tmp/doctor_dev.sh install-panel --admin-user admin --panel-port 8080

PANEL_APP_DIR="${DOCTOR_DEV_APP_DIR:-/opt/doctor-dev-panel}"
PANEL_SERVICE_NAME="${DOCTOR_DEV_SERVICE_NAME:-doctor-dev-panel}"
REPO_URL="${DOCTOR_DEV_REPO_URL:-https://github.com/alirezarohollahi/doctor_dev.git}"
RAW_INSTALLER_URL="${DOCTOR_DEV_INSTALLER_URL:-https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh}"
BRANCH="${DOCTOR_DEV_BRANCH:-master}"
PANEL_CONFIG_DIR="${DOCTOR_DEV_CONFIG_DIR:-/etc/doctor-dev-panel}"
PANEL_DATA_DIR="${DOCTOR_DEV_DATA_DIR:-/var/lib/doctor-dev-panel}"
PANEL_LOG_DIR="${DOCTOR_DEV_LOG_DIR:-/var/log/doctor-dev-panel}"
PANEL_ENV_FILE="${DOCTOR_DEV_ENV_FILE:-$PANEL_CONFIG_DIR/panel.env}"
ADMIN_STORE_PATH="${ADMIN_STORE_PATH:-$PANEL_CONFIG_DIR/admins.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

FLAG_YES=0
FLAG_PURGE=0
FLAG_CLEAN_EXISTING=0
ARG_TARGET=""
ARG_BIND_HOST=""
ARG_PUBLIC_HOST=""
ARG_PANEL_PORT=""
ARG_ADMIN_USER=""
ARG_ADMIN_PASSWORD=""
ARG_NODE_CLI_NAME=""
ARG_API_KEY=""
ARG_NODE_HOST=""
ARG_API_PORT=""
ARG_DEBUG=""

BOLD="\033[1m"; DIM="\033[2m"; RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; MAGENTA="\033[35m"; CYAN="\033[36m"; RESET="\033[0m"
cecho(){ printf "%b\n" "$1" >&2; }
info(){ cecho "${BLUE}➜${RESET} $1"; }
ok(){ cecho "${GREEN}✓${RESET} $1"; }
warn(){ cecho "${YELLOW}⚠${RESET} $1"; }
fail(){ cecho "${RED}✗${RESET} $1"; exit 1; }

need_root(){ [[ "${EUID}" -eq 0 ]] || fail "Please run this script with sudo/root."; }

hr(){ cecho "${DIM}────────────────────────────────────────────────────────────${RESET}"; }
box(){
  local title="${1:-Doctor Dev}" subtitle="${2:-}"
  cecho "${CYAN}${BOLD}╭──────────────────────────────────────────────────────────╮${RESET}"
  cecho "${CYAN}${BOLD}│${RESET} ${BOLD}${title}${RESET}"
  [[ -n "$subtitle" ]] && cecho "${CYAN}${BOLD}│${RESET} ${DIM}${subtitle}${RESET}"
  cecho "${CYAN}${BOLD}╰──────────────────────────────────────────────────────────╯${RESET}"
}
header(){
  local title="${1:-Doctor Dev}" subtitle="${2:-Installer}"
  clear 2>/dev/null || true
  box "$title" "$subtitle"
  echo >&2
}
step(){ cecho "${MAGENTA}${BOLD}▶ $1${RESET}"; }
subtle(){ cecho "${DIM}$1${RESET}"; }

usage(){
  header "Doctor Dev Installer" "Panel / node install, update, remove"
  cecho "${BOLD}Usage:${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}install-panel${RESET} [--admin-user USER] [--admin-password PASS] [--panel-port PORT] [--public-host HOST] [--yes]"
  cecho "  sudo bash doctor_dev.sh ${GREEN}update-panel${RESET} [--yes]"
  cecho "  sudo bash doctor_dev.sh ${GREEN}uninstall-panel${RESET} [--purge] [--yes]"
  cecho "  sudo bash doctor_dev.sh ${GREEN}install-node${RESET} [--node-cli-name doctor-node] [--api-port PORT] [--debug true] [--yes]  ${DIM}# single API port${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}update-node${RESET} [--node-cli-name doctor-node]"
  cecho "  sudo bash doctor_dev.sh ${GREEN}uninstall-node${RESET} [--node-cli-name doctor-node] [--purge] [--yes]"
  echo
  cecho "${BOLD}Remote usage:${RESET}"
  cecho "  curl -fsSL $RAW_INSTALLER_URL -o /tmp/doctor_dev.sh \\\n    && sudo bash /tmp/doctor_dev.sh install-panel --admin-user admin --panel-port 8080"
}

need_arg(){ [[ $# -ge 2 && -n "${2:-}" ]] || fail "Missing value for $1"; }

parse_common_args(){
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes|-y) FLAG_YES=1; shift ;;
      --purge) FLAG_PURGE=1; shift ;;
      --clean-existing) FLAG_CLEAN_EXISTING=1; shift ;;
      --target) need_arg "$@"; ARG_TARGET="$2"; shift 2 ;;
      --bind-host|--host) need_arg "$@"; ARG_BIND_HOST="$2"; shift 2 ;;
      --public-host|--domain|--ip) need_arg "$@"; ARG_PUBLIC_HOST="$2"; shift 2 ;;
      --panel-port|--port) need_arg "$@"; ARG_PANEL_PORT="$2"; shift 2 ;;
      --admin-user|--admin-username) need_arg "$@"; ARG_ADMIN_USER="$2"; shift 2 ;;
      --admin-password|--password) need_arg "$@"; ARG_ADMIN_PASSWORD="$2"; shift 2 ;;
      --node-cli-name|--cli-name) need_arg "$@"; ARG_NODE_CLI_NAME="$2"; shift 2 ;;
      --api-key) need_arg "$@"; ARG_API_KEY="$2"; shift 2 ;;
      --node-host) need_arg "$@"; ARG_NODE_HOST="$2"; shift 2 ;;
      --service-port|--node-port) need_arg "$@"; warn "--service-port is legacy and ignored. Inbound listener ports are configured in the panel."; shift 2 ;;
      --api-port) need_arg "$@"; ARG_API_PORT="$2"; shift 2 ;;
      --service-protocol|--protocol) need_arg "$@"; warn "--service-protocol is legacy and ignored. Node uses one HTTP API plus runtime listeners."; shift 2 ;;
      --debug) need_arg "$@"; ARG_DEBUG="$2"; shift 2 ;;
      --help|-h) usage; exit 0 ;;
      *) fail "Unknown parameter: $1" ;;
    esac
  done
}

prompt_read(){
  local prompt="$1" default="${2:-}" secret="${3:-0}" value=""
  local rendered
  if [[ -n "$default" ]]; then
    rendered=$(printf "%b" "${CYAN}?${RESET} ${prompt} ${DIM}[${default}]${RESET}: ")
  else
    rendered=$(printf "%b" "${CYAN}?${RESET} ${prompt}: ")
  fi
  if [[ "$secret" == "1" ]]; then
    read -r -s -p "$rendered" value || true
    echo >&2
    printf '%s\n' "$value"
    return
  fi
  # -e enables readline, so Left/Right arrows work instead of printing ^[[D/^[[C.
  if [[ -t 0 && -n "$default" ]]; then
    read -r -e -i "$default" -p "$rendered" value || true
  elif [[ -t 0 ]]; then
    read -r -e -p "$rendered" value || true
  else
    read -r value || true
  fi
  [[ -z "$value" && -n "$default" ]] && value="$default"
  printf '%s\n' "$value"
}

ask(){ prompt_read "$1" "${2:-}" 0; }

ask_yes_no(){
  local prompt="$1" default="${2:-y}" answer
  if [[ "$FLAG_YES" == "1" ]]; then return 0; fi
  while true; do
    answer="$(prompt_read "$prompt" "$default" 0)"
    answer="${answer:-$default}"
    case "${answer,,}" in y|yes) return 0 ;; n|no) return 1 ;; *) warn "Please answer y or n." ;; esac
  done
}

ask_non_empty(){
  local prompt="$1" default="${2:-}" value
  while true; do
    value="$(ask "$prompt" "$default")"
    [[ -n "$value" ]] && { printf '%s\n' "$value"; return; }
    warn "This value cannot be empty."
  done
}

ask_password(){
  local pass1 pass2
  if [[ -n "$ARG_ADMIN_PASSWORD" ]]; then
    [[ ${#ARG_ADMIN_PASSWORD} -ge 8 ]] || fail "--admin-password must be at least 8 characters."
    printf '%s\n' "$ARG_ADMIN_PASSWORD"
    return
  fi
  while true; do
    pass1="$(prompt_read "Admin password" "" 1)"
    [[ ${#pass1} -ge 8 ]] || { warn "Password must be at least 8 characters."; continue; }
    pass2="$(prompt_read "Repeat admin password" "" 1)"
    [[ "$pass1" == "$pass2" ]] || { warn "Passwords do not match."; continue; }
    printf '%s\n' "$pass1"; return
  done
}

valid_cli_name(){ [[ "$1" =~ ^[a-zA-Z0-9._-]+$ ]]; }
valid_hostname(){ [[ -n "$1" && "$1" != *"/"* && "$1" != *" "* ]]; }
valid_port(){ [[ "$1" =~ ^[0-9]+$ ]] && (( "$1" >= 1 && "$1" <= 65535 )); }

port_available(){
  local host="$1" port="$2"
  "$PYTHON_BIN" - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket, sys
host = sys.argv[1]
port = int(sys.argv[2])
probe_host = "0.0.0.0" if host in {"", "0.0.0.0", "::"} else host
families = [socket.AF_INET]
for family in families:
    s = socket.socket(family, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((probe_host, port))
    except OSError:
        sys.exit(1)
    finally:
        s.close()
PY
}

service_for_pid(){
  local pid="$1" unit mainpid
  systemctl_exists || return 1
  while IFS= read -r unit; do
    [[ -n "$unit" ]] || continue
    mainpid="$(systemctl show "$unit" -p MainPID --value 2>/dev/null || true)"
    [[ "$mainpid" == "$pid" ]] && { printf '%s\n' "${unit%.service}"; return 0; }
  done < <(systemctl list-units --type=service --all --no-legend 2>/dev/null | awk '{gsub(/^●/,"",$1); print $1}')
  return 1
}

port_pids(){
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltnp "sport = :$port" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
  elif command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
  elif command -v fuser >/dev/null 2>&1; then
    fuser "${port}/tcp" 2>/dev/null | tr ' ' '\n' | awk 'NF' | sort -u
  fi
}

pid_is_doctor_dev(){
  local pid="$1" args cwd exe
  args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
  exe="$(readlink "/proc/$pid/exe" 2>/dev/null || true)"
  [[ "$args $cwd $exe" =~ doctor[-_]dev[-_]panel|doctor_dev_panel|doctor[-_]dev[-_]node|doctor_dev_node|doctor-node|docter-node|/opt/doctor-dev-node|/opt/docter-node|/etc/doctor-dev-node|/etc/docter-node ]]
}

port_usage_details(){
  local host="$1" port="$2" pid cmd unit
  warn "Port $port is already in use on $host."
  if command -v ss >/dev/null 2>&1; then
    subtle "Listener detail from ss:"
    ss -H -ltnp "sport = :$port" 2>/dev/null | sed 's/^/  /' >&2 || true
  fi
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    unit="$(service_for_pid "$pid" 2>/dev/null || true)"
    cecho "${YELLOW}  PID:${RESET} $pid"
    [[ -n "$unit" ]] && cecho "${YELLOW}  Service:${RESET} $unit"
    [[ -n "$cmd" ]] && cecho "${YELLOW}  Command:${RESET} $cmd"
  done < <(port_pids "$port")
}

kill_pid_safely(){
  local pid="$1" cmd
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] || return 0
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ -n "$cmd" ]] || return 0
  info "Stopping process PID $pid"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    ps -p "$pid" >/dev/null 2>&1 || return 0
    sleep 0.2
  done
  warn "Process $pid did not stop gracefully; killing it."
  kill -KILL "$pid" 2>/dev/null || true
}

stop_doctor_processes_on_port(){
  local port="$1" pid unit stopped=0
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if pid_is_doctor_dev "$pid"; then
      unit="$(service_for_pid "$pid" 2>/dev/null || true)"
      if [[ -n "$unit" ]]; then
        info "Stopping Doctor Dev service using port $port: $unit"
        stop_disable_service "$unit"
      else
        kill_pid_safely "$pid"
      fi
      stopped=1
    fi
  done < <(port_pids "$port")
  [[ "$stopped" == "1" ]]
}

handle_busy_port(){
  local label="$1" host="$2" port="$3"
  port_usage_details "$host" "$port"
  if stop_doctor_processes_on_port "$port"; then
    sleep 0.5
    if port_available "$host" "$port"; then
      ok "$label $port was freed by stopping the old Doctor Dev process/service."
      return 0
    fi
    warn "$label $port is still busy after cleanup."
  fi
  return 1
}

ask_port_named(){
  local label="$1" default="$2" bind_host="${3:-0.0.0.0}" value
  while true; do
    value="$(ask "$label" "$default")"
    if ! valid_port "$value"; then warn "Invalid port. Use a number between 1 and 65535."; continue; fi
    if port_available "$bind_host" "$value"; then
      printf '%s\n' "$value"; return
    fi
    handle_busy_port "$label" "$bind_host" "$value" && { printf '%s\n' "$value"; return; }
    warn "Choose another port for $label."
  done
}

require_port_available_or_fail(){
  local label="$1" host="$2" port="$3"
  valid_port "$port" || fail "Invalid $label: $port. Use a number between 1 and 65535."
  port_available "$host" "$port" && return 0
  handle_busy_port "$label" "$host" "$port" && return 0
  fail "$label $port is already used. See the process/service details above."
}

generate_uuid(){ "$PYTHON_BIN" - <<'PY'
import uuid
print(uuid.uuid4())
PY
}

install_packages(){
  info "Checking OS packages..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip git curl nano rsync
  else
    warn "apt-get not found. Make sure python3, venv, pip, git, curl and rsync are installed."
  fi
}

systemctl_exists(){ command -v systemctl >/dev/null 2>&1; }
service_known(){
  local service="$1"
  systemctl_exists || return 1
  systemctl status "${service}.service" >/dev/null 2>&1 && return 0
  systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "${service}.service" && return 0
  systemctl list-units --all --type=service --no-legend 2>/dev/null | awk '{gsub(/^●/,"",$1); print $1}' | grep -qx "${service}.service" && return 0
  return 1
}
stop_disable_service(){
  local service="$1"
  if systemctl_exists; then
    systemctl stop "$service" 2>/dev/null || true
    systemctl disable "$service" 2>/dev/null || true
    rm -f "/etc/systemd/system/${service}.service"
    systemctl daemon-reload 2>/dev/null || true
  fi
}

collect_doctor_process_items(){
  local kind="$1" pattern pid args
  if [[ "$kind" == "panel" ]]; then
    pattern='doctor-dev-panel|doctor_dev_panel|/opt/doctor-dev-panel|/etc/doctor-dev-panel/panel.env|Doctor Dev Panel'
  else
    pattern='doctor-dev-node|doctor_dev_node|doctor_dev_node.server|doctor-node|docter-node|/opt/doctor-node|/opt/docter-node|/opt/doctor-dev-node|/etc/doctor-node|/etc/docter-node|/etc/doctor-dev-node|Doctor Dev Node'
  fi
  while IFS= read -r line; do
    pid="${line%% *}"
    args="${line#* }"
    [[ "$pid" == "$$" ]] && continue
    [[ "$args" == *grep* ]] && continue
    printf 'process:%s\n' "$pid"
  done < <(ps -eo pid=,args= | awk '{$1=$1; print}' | grep -E "$pattern" || true)
}

collect_doctor_service_items(){
  local kind="$1" pattern unit name content
  if ! systemctl_exists; then return 0; fi
  if [[ "$kind" == "panel" ]]; then
    pattern='doctor-dev-panel|doctor_dev_panel|/opt/doctor-dev-panel|/etc/doctor-dev-panel|Doctor Dev Panel'
  else
    pattern='doctor-dev-node|doctor_dev_node|doctor_dev_node.server|doctor-node|docter-node|/opt/doctor-node|/opt/docter-node|/opt/doctor-dev-node|/etc/doctor-node|/etc/docter-node|/etc/doctor-dev-node|Doctor Dev Node'
  fi
  {
    systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}'
    systemctl list-units --all --type=service --no-legend 2>/dev/null | awk '{gsub(/^●/,"",$1); print $1}'
    find /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system -maxdepth 1 -type f -name '*.service' -printf '%f\n' 2>/dev/null
  } | awk 'NF && !seen[$0]++' | while IFS= read -r unit; do
    [[ -n "$unit" ]] || continue
    name="${unit%.service}"
    if [[ "$unit $name" =~ $pattern ]]; then
      printf 'systemd:%s\n' "$name"
      continue
    fi
    content="$(systemctl cat "$unit" 2>/dev/null | head -c 20000 || true)"
    [[ "$content" =~ $pattern ]] && printf 'systemd:%s\n' "$name"
  done
}

collect_node_dynamic_paths(){
  local root
  for root in /opt /etc /var/lib /var/log; do
    [[ -d "$root" ]] || continue
    find "$root" -maxdepth 1 \( -iname '*doctor*node*' -o -iname '*docter*node*' \) -print 2>/dev/null
  done
  find /usr/local/bin -maxdepth 1 \( -iname '*doctor*node*' -o -iname '*docter*node*' \) -print 2>/dev/null || true
}

collect_existing_paths(){
  local kind="$1"; shift
  local -a names=("$@")
  local -a found=()
  local name path service
  if [[ "$kind" == "panel" ]]; then
    for path in "$PANEL_APP_DIR" "$PANEL_CONFIG_DIR" "$PANEL_DATA_DIR" "$PANEL_LOG_DIR" "/opt/doctor-dev" "/etc/doctor-dev" "/var/lib/doctor-dev" "/var/log/doctor-dev" "/usr/local/bin/doctor-dev"; do
      [[ -e "$path" || -L "$path" ]] && found+=("$path")
    done
    for service in "$PANEL_SERVICE_NAME" "doctor-dev" "doctor-dev-panel"; do
      [[ -e "/etc/systemd/system/${service}.service" ]] && found+=("/etc/systemd/system/${service}.service")
      service_known "$service" && found+=("systemd:${service}")
    done
  else
    for name in "${names[@]}" "doctor-node" "docter-node" "doctor-dev-node"; do
      for path in "/opt/${name}" "/etc/${name}" "/var/lib/${name}" "/var/log/${name}" "/usr/local/bin/${name}"; do
        [[ -e "$path" || -L "$path" ]] && found+=("$path")
      done
      [[ -e "/etc/systemd/system/${name}.service" ]] && found+=("/etc/systemd/system/${name}.service")
      service_known "$name" && found+=("systemd:${name}")
    done
    while IFS= read -r svc; do [[ -n "$svc" ]] && found+=("systemd:${svc%.service}"); done < <(find /etc/systemd/system -maxdepth 1 -type f -name 'doctor-dev-node*.service' -printf '%f\n' 2>/dev/null || true)
    while IFS= read -r path; do [[ -n "$path" ]] && found+=("$path"); done < <(collect_node_dynamic_paths)
  fi
  while IFS= read -r svc_item; do [[ -n "$svc_item" ]] && found+=("$svc_item"); done < <(collect_doctor_service_items "$kind")
  while IFS= read -r proc_item; do [[ -n "$proc_item" ]] && found+=("$proc_item"); done < <(collect_doctor_process_items "$kind")
  printf '%s\n' "${found[@]}" | awk 'NF && !seen[$0]++'
}

show_found_items(){
  local title="$1"; shift
  local -a items=("$@")
  [[ ${#items[@]} -eq 0 ]] && return 0
  cecho "${MAGENTA}${BOLD}${title}${RESET}"
  local item
  for item in "${items[@]}"; do
    if [[ "$item" == process:* ]]; then
      local pid="${item#process:}" cmd unit
      cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
      unit="$(service_for_pid "$pid" 2>/dev/null || true)"
      cecho "  - process:$pid${unit:+ service:$unit}"
      [[ -n "$cmd" ]] && subtle "      $cmd"
    else
      cecho "  - ${item}"
    fi
  done
}

remove_found_items(){
  local item svc
  for item in "$@"; do
    if [[ "$item" == systemd:* ]]; then
      svc="${item#systemd:}"
      info "Removing service: $svc"
      stop_disable_service "$svc"
    elif [[ "$item" == process:* ]]; then
      local pid="${item#process:}" unit
      unit="$(service_for_pid "$pid" 2>/dev/null || true)"
      if [[ -n "$unit" ]]; then
        info "Stopping process service: $unit"
        stop_disable_service "$unit"
      else
        kill_pid_safely "$pid"
      fi
    else
      info "Removing: $item"
      rm -rf --one-file-system "$item" 2>/dev/null || rm -rf "$item"
    fi
  done
}

clean_existing_or_fail(){
  local kind="$1"; shift
  local -a items=()
  step "Deep ${kind} scan"
  subtle "Scanning services, processes, app dirs, config dirs, data dirs, log dirs and old CLI names..."
  mapfile -t items < <(collect_existing_paths "$kind" "$@")
  if [[ ${#items[@]} -eq 0 ]]; then ok "No previous ${kind} installation was found."; return; fi
  show_found_items "Previous ${kind} installation items found:" "${items[@]}"
  if [[ "$FLAG_CLEAN_EXISTING" == "1" ]] || ask_yes_no "Remove these items before installation?" "y"; then
    remove_found_items "${items[@]}"
    ok "Previous ${kind} items removed."
  else
    fail "Installation stopped. Re-run after cleanup or use --clean-existing."
  fi
}

prepare_panel_dirs(){ mkdir -p "$PANEL_CONFIG_DIR" "$PANEL_DATA_DIR" "$PANEL_LOG_DIR"; chmod 700 "$PANEL_CONFIG_DIR" || true; chmod 755 "$PANEL_DATA_DIR" "$PANEL_LOG_DIR" || true; }

copy_from_current_tree(){
  local target_dir="$1" src_dir
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -f "$src_dir/main.py" && -d "$src_dir/doctor_dev_panel" && -d "$src_dir/doctor_dev_node" ]]; then
    info "Installing from local source: $src_dir"
    mkdir -p "$target_dir"
    rsync -a --delete --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '.env' "$src_dir/" "$target_dir/" 2>/dev/null || cp -a "$src_dir/." "$target_dir/"
    return 0
  fi
  return 1
}

clone_or_update_repo(){
  local target_dir="$1" mode="${2:-update}"
  if copy_from_current_tree "$target_dir"; then return; fi
  if [[ "$mode" == "clean" && -e "$target_dir" ]]; then rm -rf --one-file-system "$target_dir" 2>/dev/null || rm -rf "$target_dir"; fi
  if [[ -d "$target_dir/.git" ]]; then
    info "Updating repository in $target_dir"
    git -C "$target_dir" fetch origin "$BRANCH" --prune
    git -C "$target_dir" checkout "$BRANCH"
    git -C "$target_dir" reset --hard "origin/$BRANCH"
  else
    [[ -e "$target_dir" ]] && rm -rf --one-file-system "$target_dir" 2>/dev/null || true
    info "Cloning $REPO_URL#$BRANCH into $target_dir"
    git clone --branch "$BRANCH" "$REPO_URL" "$target_dir"
  fi
}

validate_project_tree(){
  local target_dir="$1"
  [[ -f "$target_dir/main.py" ]] || fail "Project is incomplete: $target_dir/main.py not found."
  [[ -d "$target_dir/doctor_dev_panel" ]] || fail "Project is incomplete: $target_dir/doctor_dev_panel package not found."
  [[ -d "$target_dir/doctor_dev_node" ]] || fail "Project is incomplete: $target_dir/doctor_dev_node package not found."
  [[ -f "$target_dir/requirements.txt" ]] || fail "Project is incomplete: $target_dir/requirements.txt not found."
  [[ -f "$target_dir/scripts/doctor-dev" ]] || fail "Project is incomplete: $target_dir/scripts/doctor-dev not found."
  [[ -f "$target_dir/scripts/doctor-node" ]] || fail "Project is incomplete: $target_dir/scripts/doctor-node not found."
}

setup_venv(){
  local target_dir="$1"
  info "Creating/updating Python virtualenv in $target_dir/.venv"
  "$PYTHON_BIN" -m venv "$target_dir/.venv"
  "$target_dir/.venv/bin/python" -m pip install --upgrade pip wheel
  "$target_dir/.venv/bin/pip" install -r "$target_dir/requirements.txt"
  PYTHONPATH="$target_dir" "$target_dir/.venv/bin/python" -c 'import doctor_dev_panel, doctor_dev_node; print("import ok")' >/dev/null || fail "Python package import failed."
  ok "Python dependencies installed."
}

generate_panel_secret(){ PYTHONPATH="$PANEL_APP_DIR" "$PANEL_APP_DIR/.venv/bin/python" -c 'from doctor_dev_panel.security import generate_secret; print(generate_secret())'; }

create_admin_store(){
  local username="$1" password="$2"
  info "Creating admin store: $ADMIN_STORE_PATH"
  ADMIN_STORE_PATH="$ADMIN_STORE_PATH" DOCTOR_DEV_BOOTSTRAP_ADMIN="$username" DOCTOR_DEV_BOOTSTRAP_PASSWORD="$password" \
    PYTHONPATH="$PANEL_APP_DIR" "$PANEL_APP_DIR/.venv/bin/python" - <<'PY'
import os, sys
from doctor_dev_panel.admin_store import authenticate_admin, set_password, store_path
username = os.environ["DOCTOR_DEV_BOOTSTRAP_ADMIN"].strip()
password = os.environ["DOCTOR_DEV_BOOTSTRAP_PASSWORD"]
set_password(username, password)
if not authenticate_admin(username, password):
    raise SystemExit(f"admin verification failed for {username} at {store_path()}")
print(f"admin verification ok: {username} -> {store_path()}")
PY
  chmod 600 "$ADMIN_STORE_PATH" || true
  ok "Admin user saved and verified."
}

write_panel_env(){
  local host="$1" port="$2" public_host="$3" public_scheme="http"
  local debug_value="${ARG_DEBUG:-${DEBUG:-false}}"
  case "${debug_value,,}" in 1|true|yes|on|debug|enabled) debug_value="true" ;; *) debug_value="false" ;; esac
  prepare_panel_dirs
  info "Writing $PANEL_ENV_FILE"
  cat > "$PANEL_ENV_FILE" <<ENV
APP_NAME=DoctorDevPanel
APP_ENV=production
APP_SECRET=$(generate_panel_secret)

HOST=$host
PORT=$port
PUBLIC_HOST=$public_host
PUBLIC_SCHEME=$public_scheme

SESSION_COOKIE=doctor_dev_session
SESSION_TTL_SECONDS=43200
COOKIE_SECURE=0

ADMIN_STORE_PATH=$ADMIN_STORE_PATH
DOCTOR_DEV_DATA_DIR=$PANEL_DATA_DIR
DOCTOR_DEV_LOG_DIR=$PANEL_LOG_DIR
DOCTOR_DEV_PANEL_LOG_FILE=$PANEL_LOG_DIR/panel.log
DOCTOR_DEV_NODES_PATH=$PANEL_DATA_DIR/nodes.json
DOCTOR_DEV_CORES_PATH=$PANEL_DATA_DIR/cores.json
DEBUG=$debug_value
PYTHON_LOG_LEVEL=INFO
UVICORN_LOG_LEVEL=info
ENV
  chmod 600 "$PANEL_ENV_FILE"
  ln -sfn "$PANEL_ENV_FILE" "$PANEL_APP_DIR/.env" 2>/dev/null || true
  ok "Environment saved."
}

install_panel_cli(){ info "Installing panel CLI: /usr/local/bin/doctor-dev"; install -m 0755 "$PANEL_APP_DIR/scripts/doctor-dev" /usr/local/bin/doctor-dev; ok "CLI installed."; }

write_panel_service(){
  info "Writing systemd service: $PANEL_SERVICE_NAME"
  cat > "/etc/systemd/system/${PANEL_SERVICE_NAME}.service" <<SERVICE
[Unit]
Description=Doctor Dev Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PANEL_APP_DIR
Environment=DOCTOR_DEV_ENV=$PANEL_ENV_FILE
Environment=PYTHONPATH=$PANEL_APP_DIR
ExecStart=$PANEL_APP_DIR/.venv/bin/python $PANEL_APP_DIR/main.py --env $PANEL_ENV_FILE
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30
User=root

[Install]
WantedBy=multi-user.target
SERVICE
  systemctl daemon-reload
  ok "Service file is ready."
}

install_panel_service(){ write_panel_service; systemctl enable "$PANEL_SERVICE_NAME" >/dev/null; systemctl restart "$PANEL_SERVICE_NAME"; ok "Panel service started."; }

install_panel(){
  header "Doctor Dev Panel Installer" "Clean install with verified admin and data integrity safeguards"
  need_root
  step "1/8 Scan and remove previous panel installation"
  clean_existing_or_fail panel
  step "2/8 Check system packages"
  install_packages
  step "3/8 Install project files"
  clone_or_update_repo "$PANEL_APP_DIR" "clean"
  validate_project_tree "$PANEL_APP_DIR"
  step "4/8 Prepare Python environment"
  setup_venv "$PANEL_APP_DIR"

  step "5/8 Configure panel endpoint"
  local target_choice install_target public_host bind_host port admin_user admin_pass public_scheme
  target_choice="${ARG_TARGET:-}"
  if [[ -z "$target_choice" ]]; then
    cecho "${BOLD}Install target${RESET}"; cecho "  1) Install on IP"; cecho "  2) Install on domain"; cecho "  3) Localhost only"
    target_choice="$(ask "Choose target" "1")"
  fi
  case "${target_choice,,}" in
    2|domain) install_target="domain"; public_host="${ARG_PUBLIC_HOST:-$(ask_non_empty "Domain" "panel.example.com")}"; bind_host="0.0.0.0" ;;
    3|local|localhost) install_target="localhost"; public_host="127.0.0.1"; bind_host="127.0.0.1" ;;
    *) install_target="ip"; public_host="${ARG_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)}"; public_host="$(valid_hostname "$public_host" && echo "$public_host" || ask_non_empty "Server IP or public host" "127.0.0.1")"; bind_host="0.0.0.0" ;;
  esac
  bind_host="${ARG_BIND_HOST:-$(ask "Bind host" "$bind_host")}"; valid_hostname "$bind_host" || fail "Invalid bind host: $bind_host"
  if [[ -n "$ARG_PANEL_PORT" ]]; then
    require_port_available_or_fail "Panel port" "$bind_host" "$ARG_PANEL_PORT"
    port="$ARG_PANEL_PORT"
  else
    port="$(ask_port_named "Panel port" "8080" "$bind_host")"
  fi
  step "6/8 Configure admin account"
  admin_user="${ARG_ADMIN_USER:-$(ask_non_empty "Admin username" "admin")}"; [[ -n "$admin_user" ]] || fail "Admin username cannot be empty."
  admin_pass="$(ask_password)"
  public_scheme="http"
  step "7/8 Write environment and verify admin password"
  write_panel_env "$bind_host" "$port" "$public_host" "$public_scheme"
  create_admin_store "$admin_user" "$admin_pass"
  step "8/8 Install CLI and service"
  install_panel_cli
  if ask_yes_no "Install and start systemd service now?" "y"; then install_panel_service; else write_panel_service; warn "Service was not started. Start later with: doctor-dev start"; fi
  echo; ok "Doctor Dev Panel installation finished."; cecho "${BOLD}Panel:${RESET} ${GREEN}${public_scheme}://${public_host}:${port}${RESET}"; cecho "${BOLD}CLI:${RESET}   ${GREEN}doctor-dev help${RESET}"
}

update_panel(){
  header "Doctor Dev Panel Updater" "Pull latest code, keep config, reinstall service, restart"
  need_root; stop_disable_service "$PANEL_SERVICE_NAME"; install_packages
  clone_or_update_repo "$PANEL_APP_DIR" "update"; validate_project_tree "$PANEL_APP_DIR"; setup_venv "$PANEL_APP_DIR"; install_panel_cli
  if [[ -f "$PANEL_ENV_FILE" ]]; then
    ln -sfn "$PANEL_ENV_FILE" "$PANEL_APP_DIR/.env" 2>/dev/null || true
    write_panel_service
    systemctl enable "$PANEL_SERVICE_NAME" >/dev/null
    systemctl restart "$PANEL_SERVICE_NAME"
    ok "Panel service installed/enabled/restarted: $PANEL_SERVICE_NAME"
  else
    warn "No panel environment file found at $PANEL_ENV_FILE. Run install-panel first."
  fi
  ok "Panel update finished."
}

uninstall_panel(){
  header "Doctor Dev Panel Remover" "Stop service and remove panel files"
  need_root
  local -a items=()
  mapfile -t items < <(collect_existing_paths panel)
  if [[ ${#items[@]} -eq 0 ]]; then ok "No panel installation was found."; return; fi
  show_found_items "Panel items to remove:" "${items[@]}"
  ask_yes_no "Remove these panel items?" "n" || fail "Canceled."
  remove_found_items "${items[@]}"
  if [[ "$FLAG_PURGE" == "1" ]]; then ok "Panel purge completed."; else ok "Panel service/app/config/data/log items removed."; fi
}

node_vars(){
  NODE_CLI_NAME="${DOCTOR_DEV_NODE_CLI_NAME:-doctor-node}"
  [[ -n "${1:-}" ]] && NODE_CLI_NAME="$1"
  valid_cli_name "$NODE_CLI_NAME" || fail "Invalid CLI name: $NODE_CLI_NAME. Use letters, numbers, dot, dash or underscore."
  NODE_APP_DIR="${DOCTOR_DEV_NODE_APP_DIR:-/opt/${NODE_CLI_NAME}}"
  NODE_SERVICE_NAME="${DOCTOR_DEV_NODE_SERVICE_NAME:-${NODE_CLI_NAME}}"
  NODE_CONFIG_DIR="${DOCTOR_DEV_NODE_CONFIG_DIR:-/etc/${NODE_CLI_NAME}}"
  NODE_DATA_DIR="${DOCTOR_DEV_NODE_DATA_DIR:-/var/lib/${NODE_CLI_NAME}}"
  NODE_LOG_DIR="${DOCTOR_DEV_NODE_LOG_DIR:-/var/log/${NODE_CLI_NAME}}"
  NODE_ENV_FILE="${DOCTOR_DEV_NODE_ENV_FILE:-$NODE_CONFIG_DIR/node.env}"
}

prepare_node_dirs(){ mkdir -p "$NODE_CONFIG_DIR" "$NODE_DATA_DIR" "$NODE_LOG_DIR"; chmod 700 "$NODE_CONFIG_DIR" || true; chmod 755 "$NODE_DATA_DIR" "$NODE_LOG_DIR" || true; }
install_node_cli(){ info "Installing node CLI: /usr/local/bin/$NODE_CLI_NAME"; install -m 0755 "$NODE_APP_DIR/scripts/doctor-node" "/usr/local/bin/$NODE_CLI_NAME"; ok "Node CLI installed. Try: $NODE_CLI_NAME help"; }

write_node_env(){
  local api_key="$1" node_host="$2" api_port="$3"
  local debug_value="${ARG_DEBUG:-${DEBUG:-false}}"
  case "${debug_value,,}" in 1|true|yes|on|debug|enabled) debug_value="true" ;; *) debug_value="false" ;; esac
  prepare_node_dirs
  info "Writing $NODE_ENV_FILE"
  cat > "$NODE_ENV_FILE" <<ENV
DOCTOR_DEV_MODE=node
API_KEY=$api_key
NODE_HOST=$node_host
API_PORT=$api_port
DOCTOR_DEV_NODE_DATA_DIR=$NODE_DATA_DIR
DOCTOR_DEV_NODE_LOG_DIR=$NODE_LOG_DIR
DOCTOR_DEV_NODE_LOG_FILE=$NODE_LOG_DIR/node.log
DEBUG=$debug_value
PYTHON_LOG_LEVEL=INFO
UVICORN_LOG_LEVEL=info
ENV
  chmod 600 "$NODE_ENV_FILE"
  ln -sfn "$NODE_ENV_FILE" "$NODE_APP_DIR/.env" 2>/dev/null || true
  ok "Node environment saved."
}

write_node_service(){
  info "Writing systemd service: $NODE_SERVICE_NAME"
  cat > "/etc/systemd/system/${NODE_SERVICE_NAME}.service" <<SERVICE
[Unit]
Description=Doctor Dev Node - $NODE_CLI_NAME
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$NODE_APP_DIR
Environment=DOCTOR_DEV_NODE_ENV=$NODE_ENV_FILE
Environment=PYTHONPATH=$NODE_APP_DIR
ExecStart=$NODE_APP_DIR/.venv/bin/python -m doctor_dev_node.server --env $NODE_ENV_FILE
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30
User=root

[Install]
WantedBy=multi-user.target
SERVICE
  systemctl daemon-reload
  ok "Node service file is ready."
}
install_node_service(){ write_node_service; systemctl enable "$NODE_SERVICE_NAME" >/dev/null; systemctl restart "$NODE_SERVICE_NAME"; ok "Node service started."; }

install_node(){
  header "Doctor Dev Node Installer" "Clean node install with validated ports and names"
  need_root; install_packages
  local cli_name api_default api_key node_host api_port
  cli_name="${ARG_NODE_CLI_NAME:-${DOCTOR_DEV_NODE_CLI_NAME:-doctor-node}}"; valid_cli_name "$cli_name" || fail "Invalid CLI name."
  node_vars "$cli_name"
  clean_existing_or_fail node "$cli_name"
  clone_or_update_repo "$NODE_APP_DIR" "clean"; validate_project_tree "$NODE_APP_DIR"; setup_venv "$NODE_APP_DIR"
  api_default="$(generate_uuid)"; api_key="${ARG_API_KEY:-$(ask "API_KEY" "$api_default")}"; [[ -n "$api_key" ]] || fail "API_KEY cannot be empty."
  node_host="${ARG_NODE_HOST:-$(ask "NODE_HOST" "127.0.0.1")}"; valid_hostname "$node_host" || fail "Invalid NODE_HOST: $node_host"
  if [[ -n "$ARG_API_PORT" ]]; then
    require_port_available_or_fail "API_PORT / control-plane port" "$node_host" "$ARG_API_PORT"
    api_port="$ARG_API_PORT"
  else
    api_port="$(ask_port_named "API_PORT / control-plane port" "62051" "$node_host")"
  fi
  ok "Node uses a single API_PORT. Data-plane listeners are created from inbound runtime config."
  write_node_env "$api_key" "$node_host" "$api_port"
  install_node_cli
  if ask_yes_no "Install and start node systemd service now?" "y"; then install_node_service; else write_node_service; warn "Node service was not started. Start later with: $NODE_CLI_NAME start"; fi
  echo; ok "Doctor Dev Node installation finished."; cecho "${BOLD}CLI:${RESET}   ${GREEN}$NODE_CLI_NAME help${RESET}"; cecho "${BOLD}Health:${RESET} ${GREEN}http://127.0.0.1:${api_port}/health${RESET}"
}

update_node(){
  header "Doctor Dev Node Updater" "Pull latest code, keep node config, reinstall service, restart"
  need_root; install_packages
  local cli_name
  cli_name="${ARG_NODE_CLI_NAME:-${DOCTOR_DEV_NODE_CLI_NAME:-doctor-node}}"; node_vars "$cli_name"
  stop_disable_service "$NODE_SERVICE_NAME"
  clone_or_update_repo "$NODE_APP_DIR" "update"; validate_project_tree "$NODE_APP_DIR"; setup_venv "$NODE_APP_DIR"; install_node_cli
  if [[ -f "$NODE_ENV_FILE" ]]; then
    ln -sfn "$NODE_ENV_FILE" "$NODE_APP_DIR/.env" 2>/dev/null || true
    write_node_service
    systemctl enable "$NODE_SERVICE_NAME" >/dev/null
    systemctl restart "$NODE_SERVICE_NAME"
    ok "Node service installed/enabled/restarted: $NODE_SERVICE_NAME"
  else
    warn "No node environment file found at $NODE_ENV_FILE. Run install-node first."
  fi
  ok "Node update finished."
}

uninstall_node(){
  header "Doctor Dev Node Remover" "Stop service and remove node files"
  need_root
  local cli_name
  cli_name="${ARG_NODE_CLI_NAME:-${DOCTOR_DEV_NODE_CLI_NAME:-doctor-node}}"; node_vars "$cli_name"
  local -a items=()
  mapfile -t items < <(collect_existing_paths node "$cli_name")
  if [[ ${#items[@]} -eq 0 ]]; then ok "No node installation was found."; return; fi
  show_found_items "Node items to remove:" "${items[@]}"
  ask_yes_no "Remove these node items?" "n" || fail "Canceled."
  remove_found_items "${items[@]}"
  ok "Node removal completed."
}

main(){
  local command="${1:-}"
  [[ $# -gt 0 ]] && shift || true
  parse_common_args "$@"
  case "$command" in
    install-panel) install_panel ;;
    update-panel) update_panel ;;
    uninstall-panel|remove-panel) uninstall_panel ;;
    install-node) install_node ;;
    update-node) update_node ;;
    uninstall-node|remove-node) uninstall_node ;;
    -h|--help|help|"") usage ;;
    *) usage; fail "Unknown command: $command" ;;
  esac
}

main "$@"







