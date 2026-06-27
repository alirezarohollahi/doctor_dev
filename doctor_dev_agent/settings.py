from __future__ import annotations

import os
from pathlib import Path

NODE_NAME = os.getenv("DOCTOR_DEV_NODE_NAME", "edge-node-1")
AGENT_HOST = os.getenv("DOCTOR_DEV_AGENT_HOST", "0.0.0.0")
AGENT_PORT = int(os.getenv("DOCTOR_DEV_AGENT_PORT", "9101"))
AGENT_API_KEY = os.getenv("DOCTOR_DEV_AGENT_API_KEY", "change-me-node-api-key")
DATA_DIR = Path(os.getenv("DOCTOR_DEV_AGENT_DATA_DIR", "/var/lib/doctor_dev/nodes/edge-node-1")).resolve()
LOG_DIR = Path(os.getenv("DOCTOR_DEV_LOG_DIR", "/var/log/doctor_dev/nodes/edge-node-1")).resolve()
CONFIG_DIR = Path(os.getenv("DOCTOR_DEV_AGENT_CONFIG_DIR", "/etc/doctor_dev/nodes/edge-node-1/generated")).resolve()
CERT_DIR = Path(os.getenv("DOCTOR_DEV_AGENT_CERT_DIR", "/etc/doctor_dev/certs")).resolve()
AGENT_LOG_FILE = LOG_DIR / f"agent_{NODE_NAME}.log"
LAST_CONFIG_FILE = CONFIG_DIR / f"agent_{NODE_NAME}.last_config.json"
ECHO_HOST = os.getenv("DOCTOR_DEV_ECHO_HOST", "127.0.0.1")
ECHO_PORTS = [int(item.strip()) for item in os.getenv("DOCTOR_DEV_ECHO_PORTS", "3000,3001").split(",") if item.strip()]


def ensure_dirs() -> None:
    for path in [DATA_DIR, LOG_DIR, CONFIG_DIR, CERT_DIR]:
        path.mkdir(parents=True, exist_ok=True)
