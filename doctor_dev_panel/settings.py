from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DOCTOR_DEV_DATA_DIR", "./data")).resolve()
LOG_DIR = Path(os.getenv("DOCTOR_DEV_LOG_DIR", "./logs")).resolve()
CONFIG_DIR = Path(os.getenv("DOCTOR_DEV_CONFIG_DIR", "./configs/generated")).resolve()
CERT_DIR = Path(os.getenv("DOCTOR_DEV_CERT_DIR", "./certs")).resolve()
STATE_FILE = DATA_DIR / "panel_state.json"


def ensure_dirs() -> None:
    for path in [DATA_DIR, LOG_DIR, CONFIG_DIR, CERT_DIR]:
        path.mkdir(parents=True, exist_ok=True)
