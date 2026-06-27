#!/usr/bin/env bash
set -Eeuo pipefail

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

BOLD="\033[1m"; DIM="\033[2m"; RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; MAGENTA="\033[35m"; CYAN="\033[36m"; RESET="\033[0m"
cecho(){ printf "%b\n" "$1"; }
info(){ cecho "${BLUE}➜${RESET} $1"; }
ok(){ cecho "${GREEN}✓${RESET} $1"; }
warn(){ cecho "${YELLOW}⚠${RESET} $1"; }
fail(){ cecho "${RED}✗${RESET} $1"; exit 1; }

need_root(){ [[ "${EUID}" -eq 0 ]] || fail "Please run with sudo/root."; }

header(){
  local title="${1:-Doctor Dev Installer}" subtitle="${2:-Panel and node foundation}"
  clear || true
  cecho "${CYAN}${BOLD}============================================================${RESET}"
  cecho "${CYAN}${BOLD}                 ${title}${RESET}"
  cecho "${CYAN}${BOLD}============================================================${RESET}"
  cecho "${DIM}${subtitle}${RESET}"
  echo
}

usage(){
  header "Doctor Dev Installer" "Use one script for panel and node install/update"
  cecho "${BOLD}Usage:${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}install-panel${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}update-panel${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}install-node${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}update-node${RESET}"
  echo
  cecho "${BOLD}Remote usage:${RESET}"
  cecho "  curl -fsSL $RAW_INSTALLER_URL -o /tmp/doctor_dev.sh \\\n    && sudo bash /tmp/doctor_dev.sh install-panel"
}

ask(){
  local prompt="$1" default="${2:-}" value
  if [[ -n "$default" ]]; then
    read -r -p "$(printf "%b" "${CYAN}?${RESET} ${prompt} ${DIM}[${default}]${RESET}: ")" value || true
    echo "${value:-$default}"
  else
    read -r -p "$(printf "%b" "${CYAN}?${RESET} ${prompt}: ")" value || true
    echo "$value"
  fi
}

ask_yes_no(){
  local prompt="$1" default="${2:-y}" answer
  while true; do
    read -r -p "$(printf "%b" "${CYAN}?${RESET} ${prompt} ${DIM}[${default}]${RESET}: ")" answer || true
    answer="${answer:-$default}"
    case "${answer,,}" in y|yes) return 0 ;; n|no) return 1 ;; *) warn "Please answer y or n." ;; esac
  done
}

ask_non_empty(){
  local prompt="$1" default="${2:-}" value
  while true; do
    value="$(ask "$prompt" "$default")"
    [[ -n "$value" ]] && { echo "$value"; return; }
    warn "This value cannot be empty."
  done
}

ask_port_named(){
  local label="$1" default="$2" value
  while true; do
    value="$(ask "$label" "$default")"
    if [[ "$value" =~ ^[0-9]+$ ]] && (( value >= 1 && value <= 65535 )); then echo "$value"; return; fi
    warn "Invalid port. Use a number between 1 and 65535."
  done
}

ask_password(){
  local pass1 pass2
  while true; do
    read -r -s -p "$(printf "%b" "${CYAN}?${RESET} Admin password: ")" pass1 || true; echo
    [[ ${#pass1} -ge 8 ]] || { warn "Password must be at least 8 characters."; continue; }
    read -r -s -p "$(printf "%b" "${CYAN}?${RESET} Repeat admin password: ")" pass2 || true; echo
    [[ "$pass1" == "$pass2" ]] || { warn "Passwords do not match."; continue; }
    echo "$pass1"; return
  done
}

valid_cli_name(){ [[ "$1" =~ ^[a-zA-Z0-9._-]+$ ]]; }

generate_uuid(){ "$PYTHON_BIN" - <<'PY'
import uuid
print(uuid.uuid4())
PY
}

install_packages(){
  info "Checking OS packages..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip git curl ca-certificates openssl nano rsync
  else
    warn "apt-get not found. Please make sure python3, venv, pip, git, curl, rsync and openssl are installed."
  fi
}

stop_service(){
  local service="$1"
  if command -v systemctl >/dev/null 2>&1 && systemctl list-units --all --type=service | grep -q "^${service}.service"; then
    info "Stopping existing service: $service"
    systemctl stop "$service" 2>/dev/null || true
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

backup_path(){
  local path="$1"
  if [[ -e "$path" ]]; then
    local backup="${path}.backup.$(date +%Y%m%d-%H%M%S)"
    mv "$path" "$backup"
    ok "Backup saved: $backup"
  fi
}

clone_or_update_repo(){
  local target_dir="$1" mode="${2:-update}"
  if copy_from_current_tree "$target_dir"; then return; fi
  if [[ "$mode" == "clean" && -e "$target_dir" ]]; then
    warn "Cleaning app directory: $target_dir"
    backup_path "$target_dir"
  fi
  if [[ -d "$target_dir/.git" ]]; then
    info "Updating repository in $target_dir"
    git -C "$target_dir" fetch origin "$BRANCH" --prune
    git -C "$target_dir" checkout "$BRANCH"
    git -C "$target_dir" reset --hard "origin/$BRANCH"
  else
    [[ -e "$target_dir" ]] && backup_path "$target_dir"
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
import os
from doctor_dev_panel.admin_store import set_password
set_password(os.environ["DOCTOR_DEV_BOOTSTRAP_ADMIN"], os.environ["DOCTOR_DEV_BOOTSTRAP_PASSWORD"])
PY
  chmod 600 "$ADMIN_STORE_PATH" || true
  ok "Admin user saved."
}

write_panel_env(){
  local host="$1" port="$2" public_host="$3" public_scheme="$4" use_tls="$5" cert_path="$6" key_path="$7"
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
COOKIE_SECURE=$use_tls

USE_TLS=$use_tls
SSL_CERT_PATH=$cert_path
SSL_KEY_PATH=$key_path

ADMIN_STORE_PATH=$ADMIN_STORE_PATH
DOCTOR_DEV_DATA_DIR=$PANEL_DATA_DIR
DOCTOR_DEV_LOG_DIR=$PANEL_LOG_DIR
DOCTOR_DEV_NODES_PATH=$PANEL_DATA_DIR/nodes.json
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

install_panel_service(){ write_panel_service; systemctl enable "$PANEL_SERVICE_NAME"; systemctl restart "$PANEL_SERVICE_NAME"; ok "Panel service started."; }

configure_panel_tls(){
  local install_target="$1" domain="$2" tls_choice cert_path key_path use_tls public_scheme
  use_tls="0"; public_scheme="http"; cert_path=""; key_path=""
  { echo; cecho "${BOLD}TLS / Certificate mode${RESET}"; cecho "  1) No TLS now; use http or add Nginx/Caddy later"; cecho "  2) I already have certificate/key paths"; cecho "  3) Issue certificate here with certbot standalone"; } >&2
  tls_choice="$(ask "Choose TLS mode" "1")"
  case "$tls_choice" in
    2) cert_path="$(ask_non_empty "Fullchain/cert path")"; key_path="$(ask_non_empty "Private key path")"; [[ -r "$cert_path" ]] || fail "Certificate is not readable: $cert_path"; [[ -r "$key_path" ]] || fail "Private key is not readable: $key_path"; use_tls="1"; public_scheme="https" ;;
    3) [[ "$install_target" == "domain" ]] || fail "Certbot mode requires domain install target."; command -v apt-get >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get install -y certbot; command -v certbot >/dev/null 2>&1 || fail "certbot is not installed."; warn "Make sure DNS points to this server and port 80 is open." >&2; certbot certonly --standalone -d "$domain" >&2; cert_path="/etc/letsencrypt/live/$domain/fullchain.pem"; key_path="/etc/letsencrypt/live/$domain/privkey.pem"; use_tls="1"; public_scheme="https" ;;
    *) use_tls="0"; public_scheme="http" ;;
  esac
  echo "$use_tls|$public_scheme|$cert_path|$key_path"
}

install_panel(){
  header "Doctor Dev Panel Installer" "Clean panel install with node inventory UI"
  need_root; stop_service "$PANEL_SERVICE_NAME"; install_packages; clone_or_update_repo "$PANEL_APP_DIR" "update"; validate_project_tree "$PANEL_APP_DIR"; setup_venv "$PANEL_APP_DIR"
  cecho "${BOLD}Install target${RESET}"; cecho "  1) Install on IP"; cecho "  2) Install on domain"; cecho "  3) Localhost only"
  local target_choice install_target public_host bind_host port admin_user admin_pass tls_result use_tls public_scheme cert_path key_path
  target_choice="$(ask "Choose target" "1")"
  case "$target_choice" in
    2) install_target="domain"; public_host="$(ask_non_empty "Domain" "panel.example.com")"; bind_host="0.0.0.0" ;;
    3) install_target="localhost"; public_host="127.0.0.1"; bind_host="127.0.0.1" ;;
    *) install_target="ip"; public_host="$(ask_non_empty "Server IP or public host" "$(hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)")"; bind_host="0.0.0.0" ;;
  esac
  bind_host="$(ask "Bind host" "$bind_host")"; port="$(ask_port_named "Panel port" "8080")"; admin_user="$(ask_non_empty "Admin username" "admin")"; admin_pass="$(ask_password)"
  tls_result="$(configure_panel_tls "$install_target" "$public_host")"; IFS='|' read -r use_tls public_scheme cert_path key_path <<< "$tls_result"
  write_panel_env "$bind_host" "$port" "$public_host" "$public_scheme" "$use_tls" "$cert_path" "$key_path"; create_admin_store "$admin_user" "$admin_pass"; install_panel_cli
  if ask_yes_no "Install and start systemd service now?" "y"; then install_panel_service; else write_panel_service; warn "Service was not started. Start later with: doctor-dev start"; fi
  echo; ok "Doctor Dev Panel installation finished."; cecho "${BOLD}Panel:${RESET} ${GREEN}${public_scheme}://${public_host}:${port}${RESET}"; cecho "${BOLD}CLI:${RESET}   ${GREEN}doctor-dev help${RESET}"
}

update_panel(){
  header "Doctor Dev Panel Updater" "Pull latest code, keep config, restart service"
  need_root; stop_service "$PANEL_SERVICE_NAME"; install_packages; clone_or_update_repo "$PANEL_APP_DIR" "update"; validate_project_tree "$PANEL_APP_DIR"; setup_venv "$PANEL_APP_DIR"; install_panel_cli
  if [[ -f "$PANEL_ENV_FILE" || -f "$PANEL_APP_DIR/.env" ]]; then ln -sfn "$PANEL_ENV_FILE" "$PANEL_APP_DIR/.env" 2>/dev/null || true; write_panel_service; if systemctl list-unit-files | grep -q "^${PANEL_SERVICE_NAME}.service"; then systemctl restart "$PANEL_SERVICE_NAME"; ok "Panel service restarted."; else warn "Panel service does not exist yet. Run install-panel once."; fi; else warn "No panel environment file found. Run install-panel once."; fi
  ok "Panel update finished."
}

node_vars(){
  NODE_CLI_NAME="${DOCTOR_DEV_NODE_CLI_NAME:-docter-node}"
  [[ -n "${1:-}" ]] && NODE_CLI_NAME="$1"
  valid_cli_name "$NODE_CLI_NAME" || fail "Invalid CLI name: $NODE_CLI_NAME. Use letters, numbers, dot, dash or underscore."
  NODE_APP_DIR="${DOCTOR_DEV_NODE_APP_DIR:-/opt/${NODE_CLI_NAME}}"
  NODE_SERVICE_NAME="${DOCTOR_DEV_NODE_SERVICE_NAME:-${NODE_CLI_NAME}}"
  NODE_CONFIG_DIR="${DOCTOR_DEV_NODE_CONFIG_DIR:-/etc/${NODE_CLI_NAME}}"
  NODE_DATA_DIR="${DOCTOR_DEV_NODE_DATA_DIR:-/var/lib/${NODE_CLI_NAME}}"
  NODE_LOG_DIR="${DOCTOR_DEV_NODE_LOG_DIR:-/var/log/${NODE_CLI_NAME}}"
  NODE_ENV_FILE="${DOCTOR_DEV_NODE_ENV_FILE:-$NODE_CONFIG_DIR/node.env}"
}

clean_node_name(){
  node_vars "$1"
  warn "Cleaning previous node installation for name: $NODE_CLI_NAME"
  stop_service "$NODE_SERVICE_NAME"
  if command -v systemctl >/dev/null 2>&1; then systemctl disable "$NODE_SERVICE_NAME" 2>/dev/null || true; rm -f "/etc/systemd/system/${NODE_SERVICE_NAME}.service"; systemctl daemon-reload || true; fi
  rm -f "/usr/local/bin/${NODE_CLI_NAME}"
  [[ -e "$NODE_APP_DIR" ]] && backup_path "$NODE_APP_DIR"
  [[ -e "$NODE_CONFIG_DIR" ]] && backup_path "$NODE_CONFIG_DIR"
  mkdir -p "$NODE_CONFIG_DIR" "$NODE_DATA_DIR" "$NODE_LOG_DIR"
  chmod 700 "$NODE_CONFIG_DIR" || true
}

install_node_cli(){ info "Installing node CLI: /usr/local/bin/$NODE_CLI_NAME"; install -m 0755 "$NODE_APP_DIR/scripts/doctor-node" "/usr/local/bin/$NODE_CLI_NAME"; ok "Node CLI installed. Try: $NODE_CLI_NAME help"; }

write_node_env(){
  local api_key="$1" node_host="$2" service_port="$3" service_protocol="$4" cert_file="$5" key_file="$6"
  mkdir -p "$NODE_CONFIG_DIR" "$NODE_DATA_DIR" "$NODE_LOG_DIR"
  info "Writing $NODE_ENV_FILE"
  cat > "$NODE_ENV_FILE" <<ENV
API_KEY=$api_key
NODE_HOST=$node_host
SERVICE_PORT=$service_port
SERVICE_PROTOCOL=$service_protocol
SSL_CERT_FILE=$cert_file
SSL_KEY_FILE=$key_file

DOCTOR_DEV_NODE_DATA_DIR=$NODE_DATA_DIR
DOCTOR_DEV_NODE_LOG_DIR=$NODE_LOG_DIR
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

install_node_service(){ write_node_service; systemctl enable "$NODE_SERVICE_NAME"; systemctl restart "$NODE_SERVICE_NAME"; ok "Node service started."; }

install_node(){
  header "Doctor Dev Node Installer" "Node base install without runtime forwarding logic"
  need_root; install_packages
  local cli_name api_default api_key node_host service_port service_protocol tls_choice cert_file key_file
  cli_name="$(ask "Node CLI name" "docter-node")"; valid_cli_name "$cli_name" || fail "Invalid CLI name."
  clean_node_name "$cli_name"
  clone_or_update_repo "$NODE_APP_DIR" "clean"; validate_project_tree "$NODE_APP_DIR"; setup_venv "$NODE_APP_DIR"
  api_default="$(generate_uuid)"; api_key="$(ask "API_KEY" "$api_default")"; [[ -n "$api_key" ]] || fail "API_KEY cannot be empty."
  node_host="$(ask "NODE_HOST" "127.0.0.1")"; service_port="$(ask_port_named "SERVICE_PORT" "62050")"
  while true; do service_protocol="$(ask "SERVICE_PROTOCOL" "grpc")"; service_protocol="${service_protocol,,}"; [[ "$service_protocol" == "grpc" || "$service_protocol" == "rest" ]] && break; warn "SERVICE_PROTOCOL must be grpc or rest."; done
  cert_file=""; key_file=""
  cecho "${BOLD}SSL/TLS Configuration${RESET}"; cecho "  1) No SSL/TLS now"; cecho "  2) I already have certificate/key paths"
  tls_choice="$(ask "Choose SSL/TLS mode" "1")"
  if [[ "$tls_choice" == "2" ]]; then cert_file="$(ask_non_empty "SSL_CERT_FILE")"; key_file="$(ask_non_empty "SSL_KEY_FILE")"; [[ -r "$cert_file" ]] || fail "Certificate is not readable: $cert_file"; [[ -r "$key_file" ]] || fail "Private key is not readable: $key_file"; fi
  write_node_env "$api_key" "$node_host" "$service_port" "$service_protocol" "$cert_file" "$key_file"; install_node_cli
  if ask_yes_no "Install and start node systemd service now?" "y"; then install_node_service; else write_node_service; warn "Node service was not started. Start later with: $NODE_CLI_NAME start"; fi
  echo; ok "Doctor Dev Node installation finished."; cecho "${BOLD}CLI:${RESET}   ${GREEN}$NODE_CLI_NAME help${RESET}"; cecho "${BOLD}Health:${RESET} ${GREEN}http://127.0.0.1:${service_port}/health${RESET}"
}

update_node(){
  header "Doctor Dev Node Updater" "Pull latest code, keep node config, restart service"
  need_root; install_packages
  local cli_name
  cli_name="${DOCTOR_DEV_NODE_CLI_NAME:-}"
  [[ -z "$cli_name" ]] && cli_name="$(ask "Node CLI name" "docter-node")"
  node_vars "$cli_name"
  stop_service "$NODE_SERVICE_NAME"
  clone_or_update_repo "$NODE_APP_DIR" "update"; validate_project_tree "$NODE_APP_DIR"; setup_venv "$NODE_APP_DIR"; install_node_cli
  if [[ -f "$NODE_ENV_FILE" || -f "$NODE_APP_DIR/.env" ]]; then ln -sfn "$NODE_ENV_FILE" "$NODE_APP_DIR/.env" 2>/dev/null || true; write_node_service; if systemctl list-unit-files | grep -q "^${NODE_SERVICE_NAME}.service"; then systemctl restart "$NODE_SERVICE_NAME"; ok "Node service restarted."; else warn "Node service does not exist yet. Run install-node once."; fi; else warn "No node environment file found. Run install-node once."; fi
  ok "Node update finished."
}

main(){
  local command="${1:-}"
  case "$command" in
    install-panel) install_panel ;;
    update-panel) update_panel ;;
    install-node) install_node ;;
    update-node) update_node ;;
    -h|--help|help|"") usage ;;
    *) usage; fail "Unknown command: $command" ;;
  esac
}

main "$@"
