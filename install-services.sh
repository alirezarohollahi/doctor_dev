#!/usr/bin/env bash
set -euo pipefail

# Change this if your project is not in /home/see/doctor_dev
PROJECT_DIR="${PROJECT_DIR:-/home/see/doctor_dev}"

for svc in doctor-freedom.service doctor-first.service; do
  sed "s#/home/see/doctor_dev#${PROJECT_DIR}#g" "$svc" | sudo tee "/etc/systemd/system/$svc" >/dev/null
  sudo chmod 644 "/etc/systemd/system/$svc"
done

sudo systemctl daemon-reload

echo "Installed systemd services:"
echo "  doctor-freedom.service -> ${PROJECT_DIR}/DocNodes/freedom-000-node/configs/freedom-000-node.env"
echo "  doctor-first.service   -> ${PROJECT_DIR}/DocNodes/first-000-node/configs/first-000-node.env"
echo
echo "Enable/start freedom node: sudo systemctl enable --now doctor-freedom"
echo "Enable/start first node:   sudo systemctl enable --now doctor-first"
