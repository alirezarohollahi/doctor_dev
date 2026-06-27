#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${DOCTOR_DEV_REPO_URL:-https://github.com/alirezarohollahi/doctor_dev}"
INSTALL_ROOT="${DOCTOR_DEV_INSTALL_ROOT:-/opt/doctor_dev}"
CMD="${1:-install}"

need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo bash $0 $CMD" >&2
    exit 1
  fi
}

has_cmd() { command -v "$1" >/dev/null 2>&1; }

install_base_packages() {
  if has_cmd apt-get; then
    apt-get update || true
    apt-get install -y python3 python3-venv python3-pip git curl ca-certificates openssl tar unzip
  elif has_cmd apk; then
    apk update || true
    apk add --no-cache python3 py3-pip py3-virtualenv git curl ca-certificates openssl tar unzip
  elif has_cmd dnf; then
    dnf install -y python3 python3-pip git curl ca-certificates openssl tar unzip
  elif has_cmd yum; then
    yum install -y python3 python3-pip git curl ca-certificates openssl tar unzip
  elif has_cmd zypper; then
    zypper --non-interactive refresh || true
    zypper --non-interactive install python3 python3-pip git curl ca-certificates openssl tar unzip
  elif has_cmd pacman; then
    pacman -Sy --noconfirm python python-pip git curl ca-certificates openssl tar unzip
  else
    echo "Unsupported Linux package manager. Supported: apt, apk, dnf, yum, zypper, pacman." >&2
    exit 1
  fi
}

prepare_repo() {
  mkdir -p "$(dirname "$INSTALL_ROOT")"
  if [ -d "$INSTALL_ROOT/.git" ]; then
    git -C "$INSTALL_ROOT" fetch --all || true
    git -C "$INSTALL_ROOT" pull --ff-only || true
    return
  fi
  if [ -e "$INSTALL_ROOT" ] && [ "$(find "$INSTALL_ROOT" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)" != "0" ]; then
    echo "Existing non-git directory found: $INSTALL_ROOT"
    read -r -p "Remove it and clone a fresh copy? [y/N]: " ans
    case "${ans,,}" in
      y|yes) rm -rf "$INSTALL_ROOT" ;;
      *) echo "Cancelled."; exit 1 ;;
    esac
  fi
  git clone "$REPO_URL" "$INSTALL_ROOT"
}

run_installer() {
  local installer="$1"
  python3 "$INSTALL_ROOT/scripts/$installer"
}

uninstall_all() {
  if [ -f "$INSTALL_ROOT/scripts/uninstall.py" ]; then
    python3 "$INSTALL_ROOT/scripts/uninstall.py"
  else
    systemctl disable --now doctor-dev-panel.service 2>/dev/null || true
    for service in /etc/systemd/system/doctor-dev-node-*.service; do
      [ -e "$service" ] || continue
      systemctl disable --now "$(basename "$service")" 2>/dev/null || true
      rm -f "$service"
    done
    rm -f /etc/systemd/system/doctor-dev-panel.service
    systemctl daemon-reload 2>/dev/null || true
    rm -f /usr/local/bin/doctor-panel /usr/local/bin/doctor-node
    echo "Services and CLI wrappers removed. Source/config/data were not removed."
  fi
}

need_root

case "$CMD" in
  install|install-panel)
    install_base_packages
    prepare_repo
    run_installer install_panel.py
    ;;
  install-node)
    install_base_packages
    prepare_repo
    run_installer install_node.py
    ;;
  update)
    install_base_packages
    prepare_repo
    if [ -x "$INSTALL_ROOT/.venv/bin/pip" ]; then
      "$INSTALL_ROOT/.venv/bin/pip" install -U -r "$INSTALL_ROOT/requirements.txt" || true
      "$INSTALL_ROOT/.venv/bin/pip" install -e "$INSTALL_ROOT" || true
    fi
    systemctl restart doctor-dev-panel.service 2>/dev/null || true
    for service in /etc/systemd/system/doctor-dev-node-*.service; do
      [ -e "$service" ] || continue
      systemctl restart "$(basename "$service")" 2>/dev/null || true
    done
    echo "Doctor Dev update finished."
    ;;
  uninstall)
    uninstall_all
    ;;
  *)
    echo "Usage: sudo bash doctor_dev.sh {install|install-panel|install-node|update|uninstall}" >&2
    exit 1
    ;;
esac
