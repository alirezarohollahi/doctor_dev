from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def node_data_dir() -> Path:
    path = Path(os.getenv("DOCTOR_DEV_NODE_DATA_DIR", "/var/lib/doctor-node")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def routing_config_path() -> Path:
    configured = os.getenv("DOCTOR_DEV_NODE_ROUTING_CONFIG", "").strip()
    if configured:
        return Path(configured).expanduser()
    return node_data_dir() / "routing-config.json"


def read_routing_config() -> dict[str, Any]:
    path = routing_config_path()
    if not path.exists():
        return {"version": 1, "generated_at": None, "cores": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "error": "Routing config root is not an object.", "cores": []}
    except Exception as exc:  # noqa: BLE001
        return {"version": 1, "error": f"Cannot read routing config: {exc}", "cores": []}


def write_routing_config(data: dict[str, Any]) -> None:
    path = routing_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="routing.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


