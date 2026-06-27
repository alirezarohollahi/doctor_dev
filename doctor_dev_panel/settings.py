from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DOCTOR_DEV_DATA_DIR", "/var/lib/doctor_dev/panel")).resolve()
LOG_DIR = Path(os.getenv("DOCTOR_DEV_LOG_DIR", "/var/log/doctor_dev/panel")).resolve()
CONFIG_DIR = Path(os.getenv("DOCTOR_DEV_CONFIG_DIR", "/etc/doctor_dev/panel/generated")).resolve()
CERT_DIR = Path(os.getenv("DOCTOR_DEV_CERT_DIR", "/etc/doctor_dev/certs")).resolve()
STATE_FILE = DATA_DIR / "panel_state.json"


def ensure_dirs() -> None:
    for path in [DATA_DIR, LOG_DIR, CONFIG_DIR, CERT_DIR]:
        path.mkdir(parents=True, exist_ok=True)
