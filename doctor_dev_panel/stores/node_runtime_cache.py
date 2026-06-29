from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cache_path() -> Path:
    configured = os.getenv("DOCTOR_DEV_NODE_RUNTIME_CACHE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_dir = Path(os.getenv("DOCTOR_DEV_DATA_DIR", "/var/lib/doctor-dev-panel")).expanduser()
    if os.access(str(data_dir.parent), os.W_OK) or data_dir.exists():
        return data_dir / "node-runtime-cache.json"
    return Path.cwd() / "data" / "node-runtime-cache.json"


def empty_cache() -> dict[str, Any]:
    return {"version": 1, "nodes": {}}


def load_cache() -> dict[str, Any]:
    path = cache_path()
    if not path.exists():
        return empty_cache()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty_cache()
    if not isinstance(loaded, dict):
        return empty_cache()
    loaded.setdefault("version", 1)
    if not isinstance(loaded.get("nodes"), dict):
        loaded["nodes"] = {}
    return loaded


def save_cache(data: dict[str, Any]) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="node-runtime.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        try:
            os.chmod(path, 0o600)
        except PermissionError:
            pass
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _listeners_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    listeners = payload.get("listeners") if isinstance(payload.get("listeners"), list) else summary.get("listeners")
    if not isinstance(listeners, list):
        return []
    return [item for item in listeners if isinstance(item, dict)]


def update_node_runtime(node_id: str, payload: dict[str, Any], *, source: str = "panel-sync") -> dict[str, Any]:
    node_id = str(node_id or payload.get("node_id") or "").strip()
    if not node_id:
        return empty_cache()
    data = load_cache()
    listeners = _listeners_from_payload(payload)
    now = _now()
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    data.setdefault("nodes", {})[node_id] = {
        "node_id": node_id,
        "source": source,
        "synced_at": now,
        "last_seen_at": now,
        "last_success_at": now,
        "reachable": True,
        "auth_ok": True,
        "runtime_ok": bool(payload.get("ok", True)),
        "last_error": "",
        "generated_at": payload.get("generated_at") or payload.get("config", {}).get("generated_at"),
        "exported_at": payload.get("exported_at"),
        "config_hash": summary.get("config_hash") or payload.get("config_hash"),
        "core": payload.get("core") if isinstance(payload.get("core"), dict) else summary.get("core", {}),
        "summary": summary,
        "listeners": listeners,
        "raw": payload if os.getenv("DOCTOR_DEV_STORE_FULL_NODE_RUNTIME", "false").lower() in {"1", "true", "yes", "on"} else {},
    }
    save_cache(data)
    return data


def mark_node_runtime_error(node_id: str, error: str, *, source: str = "panel-sync") -> dict[str, Any]:
    node_id = str(node_id or "").strip()
    if not node_id:
        return empty_cache()
    data = load_cache()
    nodes = data.setdefault("nodes", {})
    previous = nodes.get(node_id) if isinstance(nodes.get(node_id), dict) else {}
    now = _now()
    error_text = str(error or "Unknown runtime sync error")[:1000]
    auth_ok = "401" not in error_text and "auth" not in error_text.lower() and "api key" not in error_text.lower()
    nodes[node_id] = {
        **previous,
        "node_id": node_id,
        "source": source,
        "synced_at": now,
        "last_seen_at": now,
        "reachable": "unreachable" not in error_text.lower(),
        "auth_ok": auth_ok,
        "runtime_ok": False,
        "last_error": error_text,
    }
    save_cache(data)
    return data


def get_node_runtime(node_id: str) -> Optional[dict[str, Any]]:
    data = load_cache()
    entry = data.get("nodes", {}).get(str(node_id or ""))
    return entry if isinstance(entry, dict) else None


def find_live_inbound_ports(node_id: str, core_id: str = "", inbound_name: str = "") -> list[int]:
    entry = get_node_runtime(node_id)
    if not entry:
        return []
    ports: list[int] = []
    for listener in entry.get("listeners", []) if isinstance(entry.get("listeners"), list) else []:
        if not isinstance(listener, dict) or listener.get("status") != "listening":
            continue
        if core_id and str(listener.get("core_id") or "") != str(core_id):
            continue
        if inbound_name and str(listener.get("inbound_name") or "") != str(inbound_name):
            continue
        try:
            port = int(listener.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return ports




