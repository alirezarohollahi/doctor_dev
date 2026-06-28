from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .id_utils import is_valid_node_id

VALID_STATUSES = {"disabled", "pending", "running", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_nodes_path() -> Path:
    configured = os.getenv("DOCTOR_DEV_NODES_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_dir = Path(os.getenv("DOCTOR_DEV_DATA_DIR", "/var/lib/doctor-dev-panel")).expanduser()
    if os.access(str(data_dir.parent), os.W_OK) or data_dir.exists():
        return data_dir / "nodes.json"
    return Path.cwd() / "data" / "nodes.json"


def nodes_path() -> Path:
    return default_nodes_path().resolve()


def generate_node_id() -> str:
    return "node_" + secrets.token_hex(8)


def generate_api_key() -> str:
    return str(__import__("uuid").uuid4())


def empty_store() -> dict[str, Any]:
    return {"version": 3, "nodes": []}


def load_store() -> dict[str, Any]:
    path = nodes_path()
    if not path.exists():
        return empty_store()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Cannot read nodes store: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        return empty_store()
    loaded.setdefault("version", 3)
    if not isinstance(loaded.get("nodes"), list):
        loaded["nodes"] = []
    return loaded


def save_store(data: dict[str, Any]) -> None:
    path = nodes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="nodes.", suffix=".tmp", dir=str(path.parent))
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


def normalize_node(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now()
    base = dict(existing or {})
    base.update(payload)
    if not is_valid_node_id(base.get("id")):
        base["id"] = generate_node_id()
    base.setdefault("created_at", now)
    base["updated_at"] = now

    # Core Configuration is intentionally not part of Create Node anymore.
    base.pop("core_configuration", None)

    # New nodes are enabled by default. Existing disabled nodes remain disabled unless edited.
    base["enabled"] = bool(base.get("enabled", True))
    if not base["enabled"]:
        base["status"] = "disabled"
    else:
        status = str(base.get("status") or "pending").lower()
        base["status"] = status if status in VALID_STATUSES and status != "disabled" else "pending"
    base.setdefault("last_checked_at", None)
    base.setdefault("last_error", "")
    return base


def list_nodes() -> list[dict[str, Any]]:
    nodes = load_store().get("nodes", [])
    cleaned: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not is_valid_node_id(node.get("id")):
            continue
        cleaned.append(normalize_node(node, existing=node))
    return cleaned


def get_node(node_id: str) -> dict[str, Any] | None:
    if not is_valid_node_id(node_id):
        return None
    for node in list_nodes():
        if node.get("id") == node_id:
            return node
    return None


def create_node(payload: dict[str, Any]) -> dict[str, Any]:
    data = load_store()
    node = normalize_node(payload)
    data.setdefault("nodes", []).append(node)
    data["version"] = 3
    save_store(data)
    return node


def update_node(node_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not is_valid_node_id(node_id):
        return None
    data = load_store()
    nodes = data.setdefault("nodes", [])
    for index, node in enumerate(nodes):
        if node.get("id") == node_id:
            payload = dict(payload)
            payload["id"] = node_id
            nodes[index] = normalize_node(payload, existing=node)
            data["version"] = 3
            save_store(data)
            return nodes[index]
    return None


def set_node_check_result(node_id: str, *, ok: bool, error: str = "", details: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not is_valid_node_id(node_id):
        return None
    data = load_store()
    nodes = data.setdefault("nodes", [])
    for index, node in enumerate(nodes):
        if node.get("id") == node_id:
            updated = normalize_node(node, existing=node)
            # Health check result is stored even if the node is disabled, but disabled nodes
            # still display as Disabled until the user enables them.
            if updated.get("enabled"):
                updated["status"] = "running" if ok else "error"
            updated["last_checked_at"] = _now()
            updated["last_error"] = "" if ok else str(error or "Unknown error")[:500]
            if details is not None:
                updated["last_check_details"] = details
            nodes[index] = updated
            data["version"] = 3
            save_store(data)
            return updated
    return None


def remove_node(node_id: str) -> bool:
    if not is_valid_node_id(node_id):
        return False
    data = load_store()
    nodes = data.setdefault("nodes", [])
    next_nodes = [node for node in nodes if node.get("id") != node_id]
    if len(next_nodes) == len(nodes):
        return False
    data["nodes"] = next_nodes
    data["version"] = 3
    save_store(data)
    return True
