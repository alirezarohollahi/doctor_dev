#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${DOCTOR_DEV_APP_DIR:-/opt/doctor-dev-panel}"
SERVICE_NAME="${DOCTOR_DEV_SERVICE_NAME:-doctor-dev-panel}"
REPO_URL="${DOCTOR_DEV_REPO_URL:-https://github.com/alirezarohollahi/doctor_dev.git}"
BRANCH="${DOCTOR_DEV_BRANCH:-master}"
ENV_FILE="$APP_DIR/.env"
PYTHON_BIN="${PYTHON_BIN:-python3}"

BOLD="\033[1m"; DIM="\033[2m"; RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; MAGENTA="\033[35m"; CYAN="\033[36m"; RESET="\033[0m"

cecho() { printf "%b\n" "$1"; }
info() { cecho "${BLUE}➜${RESET} $1"; }
ok() { cecho "${GREEN}✓${RESET} $1"; }
warn() { cecho "${YELLOW}⚠${RESET} $1"; }
fail() { cecho "${RED}✗${RESET} $1"; exit 1; }

need_root() {
  [[ "${EUID}" -eq 0 ]] || fail "Please run with sudo/root. Example: sudo bash /tmp/doctor_dev.sh install-panel"
}

header() {
  clear || true
  cecho "${CYAN}${BOLD}============================================================${RESET}"
  cecho "${CYAN}${BOLD}                 Doctor Dev Panel Installer${RESET}"
  cecho "${CYAN}${BOLD}============================================================${RESET}"
  cecho "${DIM}Clean login foundation + CLI + optional systemd service${RESET}"
  echo
}

usage() {
  cecho "${BOLD}Usage:${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}install-panel${RESET}"
  cecho "  sudo bash doctor_dev.sh ${GREEN}update-panel${RESET}"
  echo
  cecho "${BOLD}Remote usage:${RESET}"
  cecho "  curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \\\n    && sudo bash /tmp/doctor_dev.sh install-panel"
}

ask() {
  local prompt="$1" default="${2:-}" value
  if [[ -n "$default" ]]; then
    read -r -p "$(printf "%b" "${CYAN}?${RESET} ${prompt} ${DIM}[${default}]${RESET}: ")" value || true
    echo "${value:-$default}"
  else
    read -r -p "$(printf "%b" "${CYAN}?${RESET} ${prompt}: ")" value || true
    echo "$value"
  fi
}

ask_yes_no() {
  local prompt="$1" default="${2:-y}" answer
  while true; do
    read -r -p "$(printf "%b" "${CYAN}?${RESET} ${prompt} ${DIM}[${default}]${RESET}: ")" answer || true
    answer="${answer:-$default}"
    case "${answer,,}" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) warn "Please answer y or n." ;;
    esac
  done
}

ask_port() {
  local value
  while true; do
    value="$(ask "Panel port" "8080")"
    if [[ "$value" =~ ^[0-9]+$ ]] && (( value >= 1 && value <= 65535 )); then
      echo "$value"; return
    fi
    warn "Invalid port. Use a number between 1 and 65535."
  done
}

ask_non_empty() {
  local prompt="$1" default="${2:-}" value
  while true; do
    value="$(ask "$prompt" "$default")"
    [[ -n "$value" ]] && { echo "$value"; return; }
    warn "This value cannot be empty."
  done
}

ask_password() {
  local pass1 pass2
  while true; do
    read -r -s -p "$(printf "%b" "${CYAN}?${RESET} Admin password: ")" pass1 || true; echo
    [[ ${#pass1} -ge 8 ]] || { warn "Password must be at least 8 characters."; continue; }
    read -r -s -p "$(printf "%b" "${CYAN}?${RESET} Repeat admin password: ")" pass2 || true; echo
    [[ "$pass1" == "$pass2" ]] || { warn "Passwords do not match."; continue; }
    echo "$pass1"; return
  done
}

install_packages() {
  info "Checking OS packages..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip git curl ca-certificates openssl nano
  else
    warn "apt-get not found. Please make sure python3, venv, pip, git, curl and openssl are installed."
  fi
}

copy_from_current_tree() {
  local src_dir
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -f "$src_dir/main.py" && -d "$src_dir/doctor_dev_panel" ]]; then
    info "Installing from local source: $src_dir"
    mkdir -p "$APP_DIR"
    rsync -a --delete --exclude '.git' --exclude '.venv' --exclude '__pycache__' "$src_dir/" "$APP_DIR/" 2>/dev/null || cp -a "$src_dir/." "$APP_DIR/"
    return 0
  fi
  return 1
}

clone_or_update_repo() {
  if copy_from_current_tree; then return; fi

  if [[ -d "$APP_DIR/.git" ]]; then
    info "Updating existing repository in $APP_DIR"
    git -C "$APP_DIR" fetch --all --prune
    git -C "$APP_DIR" checkout "$BRANCH"
    git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
  else
    if [[ -e "$APP_DIR" ]]; then
      local backup="${APP_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
      if ask_yes_no "Existing $APP_DIR found. Backup and replace it?" "y"; then
        mv "$APP_DIR" "$backup"
        ok "Backup saved: $backup"
      else
        fail "Install cancelled."
      fi
    fi
    info "Cloning $REPO_URL#$BRANCH into $APP_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  fi
}

setup_venv() {
  info "Creating Python virtualenv..."
  "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
  "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip wheel
  "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
  ok "Python dependencies installed."
}

generate_hash() {
  local password="$1"
  # The project is not installed as a pip package yet; make imports work from APP_DIR.
  PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -c 'from doctor_dev_panel.security import create_password_hash; import sys; print(create_password_hash(sys.argv[1]))' "$password"
}

generate_secret() {
  # The project is not installed as a pip package yet; make imports work from APP_DIR.
  PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -c 'from doctor_dev_panel.security import generate_secret; print(generate_secret())'
}

write_env() {
  local username="$1" password_hash="$2" host="$3" port="$4" public_host="$5" public_scheme="$6" use_tls="$7" cert_path="$8" key_path="$9"
  info "Writing $ENV_FILE"
  cat > "$ENV_FILE" <<ENV
APP_NAME=Doctor Dev Panel
APP_ENV=production
APP_SECRET=$(generate_secret)

ADMIN_USERNAME=$username
ADMIN_PASSWORD_HASH=$password_hash

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

DOCTOR_DEV_CONFIG_PATH=/etc/doctor-dev/config.json
DOCTOR_DEV_LOG_DIR=/var/log/doctor-dev
ENV
  chmod 600 "$ENV_FILE"
  ok "Environment saved."
}

install_cli() {
  info "Installing CLI: /usr/local/bin/doctor-dev"
  install -m 0755 "$APP_DIR/scripts/doctor-dev" /usr/local/bin/doctor-dev
  ok "CLI installed. Try: doctor-dev help"
}

install_service() {
  info "Installing systemd service: $SERVICE_NAME"
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<SERVICE
[Unit]
Description=Doctor Dev Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment=DOCTOR_DEV_ENV=$ENV_FILE
Environment=PYTHONPATH=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/main.py --env $ENV_FILE
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30
User=root

[Install]
WantedBy=multi-user.target
SERVICE
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"
  ok "Service started."
}

configure_tls() {
  local install_target="$1" domain="$2" tls_choice cert_path key_path use_tls public_scheme
  use_tls="0"; public_scheme="http"; cert_path=""; key_path=""
  {
    echo
    cecho "${BOLD}TLS / Certificate mode${RESET}"
    cecho "  1) No TLS now; use http or add Nginx/Caddy later"
    cecho "  2) I already have certificate/key paths"
    cecho "  3) Issue certificate here with certbot standalone"
  } >&2

  tls_choice="$(ask "Choose TLS mode" "1")"
  case "$tls_choice" in
    2)
      cert_path="$(ask_non_empty "Fullchain/cert path")"
      key_path="$(ask_non_empty "Private key path")"
      [[ -r "$cert_path" ]] || fail "Certificate is not readable: $cert_path"
      [[ -r "$key_path" ]] || fail "Private key is not readable: $key_path"
      use_tls="1"; public_scheme="https"
      ;;
    3)
      [[ "$install_target" == "domain" ]] || fail "Certbot mode requires domain install target."
      command -v apt-get >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get install -y certbot
      command -v certbot >/dev/null 2>&1 || fail "certbot is not installed."
      warn "Make sure DNS points to this server and port 80 is open." >&2
      certbot certonly --standalone -d "$domain" >&2
      cert_path="/etc/letsencrypt/live/$domain/fullchain.pem"
      key_path="/etc/letsencrypt/live/$domain/privkey.pem"
      use_tls="1"; public_scheme="https"
      ;;
    *)
      use_tls="0"; public_scheme="http"
      ;;
  esac
  echo "$use_tls|$public_scheme|$cert_path|$key_path"
}

install_panel() {
  header
  need_root
  install_packages
  clone_or_update_repo
  setup_venv

  cecho "${BOLD}Install target${RESET}"
  cecho "  1) Install on IP"
  cecho "  2) Install on domain"
  cecho "  3) Localhost only"
  local target_choice install_target public_host bind_host port admin_user admin_pass pass_hash tls_result use_tls public_scheme cert_path key_path
  target_choice="$(ask "Choose target" "1")"
  case "$target_choice" in
    2) install_target="domain"; public_host="$(ask_non_empty "Domain" "panel.example.com")"; bind_host="0.0.0.0" ;;
    3) install_target="localhost"; public_host="127.0.0.1"; bind_host="127.0.0.1" ;;
    *) install_target="ip"; public_host="$(ask_non_empty "Server IP or public host" "$(hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)")"; bind_host="0.0.0.0" ;;
  esac

  bind_host="$(ask "Bind host" "$bind_host")"
  port="$(ask_port)"
  admin_user="$(ask_non_empty "Admin username" "admin")"
  admin_pass="$(ask_password)"
  pass_hash="$(generate_hash "$admin_pass")"

  tls_result="$(configure_tls "$install_target" "$public_host")"
  IFS='|' read -r use_tls public_scheme cert_path key_path <<< "$tls_result"

  write_env "$admin_user" "$pass_hash" "$bind_host" "$port" "$public_host" "$public_scheme" "$use_tls" "$cert_path" "$key_path"
  install_cli

  if ask_yes_no "Install and start systemd service now?" "y"; then
    install_service
  else
    warn "Service not installed. You can run manually: cd $APP_DIR && .venv/bin/python main.py --env .env"
  fi

  echo
  ok "Doctor Dev Panel installation finished."
  cecho "${BOLD}Panel:${RESET} ${GREEN}${public_scheme}://${public_host}:${port}${RESET}"
  cecho "${BOLD}CLI:${RESET}   ${GREEN}doctor-dev help${RESET}"
}

update_panel() {
  header
  need_root
  install_packages
  clone_or_update_repo
  setup_venv
  install_cli
  if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
    systemctl daemon-reload
    systemctl restart "$SERVICE_NAME"
    ok "Service restarted."
  else
    warn "Service does not exist yet. Run install-panel to create it."
  fi
  ok "Update finished."
}

main() {
  local command="${1:-}"
  case "$command" in
    install-panel) install_panel ;;
    update-panel) update_panel ;;
    -h|--help|help|"") usage ;;
    *) usage; fail "Unknown command: $command" ;;
  esac
}

main "$@"
