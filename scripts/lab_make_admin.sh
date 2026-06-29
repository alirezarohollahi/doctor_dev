#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON_BIN:-./.venv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="python3"; fi
USER_NAME="${1:-admin}"
PASSWORD="${2:-admin12345}"
mkdir -p data/lab/panel logs/lab/panel
DOCTOR_DEV_ENV=env.examples/lab-panel.env "$PY" -m doctor_dev_panel.admin_cli add "$USER_NAME" --password "$PASSWORD"
echo "Admin ready: username=$USER_NAME password=$PASSWORD"
