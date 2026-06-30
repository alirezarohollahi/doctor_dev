
from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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


def generate_secret_token() -> str:
    return secrets.token_urlsafe(32)


def generate_peer_verify_secret() -> str:
    return secrets.token_urlsafe(48)


def empty_store() -> dict[str, Any]:
    return {"version": 4, "nodes": []}


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
    loaded.setdefault("version", 4)
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


def normalize_node(payload: dict[str, Any], existing: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    now = _now()
    base = dict(existing or {})
    base.update(payload)
    if not is_valid_node_id(base.get("id")):
        base["id"] = generate_node_id()
    base.setdefault("created_at", now)
    base["updated_at"] = now

    # Core Configuration is intentionally not part of Create Node anymore.
    base.pop("core_configuration", None)

    # Drop old secure-file values during normalization.
    for old_key in ("cer" + "tificate", "t" + "ls"):
        base.pop(old_key, None)

    # Node has only one management/control port now: API_PORT. Listener/data
    # ports belong to inbound runtime config, not to the node record.
    for legacy_key in (
        "node_port",
        "service_port",
        "service_protocol",
        "connection_type",
        "usage_ratio",
        "keep_alive_value",
        "keep_alive_unit",
        "data_limit_gb",
        "default_timeout",
        "internal_timeout",
        "proxy_url",
    ):
        base.pop(legacy_key, None)

    # Legacy static peer secret is intentionally removed from the node model.
    # Peer access is now granted by short-lived panel-issued tokens.
    base.pop("secret_token", None)
    if not str(base.get("peer_verify_secret") or "").strip():
        base["peer_verify_secret"] = generate_peer_verify_secret()

    # Node runtime pull interval is no longer a node-level setting.
    # It belongs to each core dependency, because B may sync A every 3s
    # while another dependency syncs on a different cadence.
    base.pop("update_interval", None)

    try:
        peer_token_refresh_interval = int(base.get("peer_token_refresh_interval") or 30)
    except (TypeError, ValueError):
        peer_token_refresh_interval = 30
    base["peer_token_refresh_interval"] = min(max(peer_token_refresh_interval, 5), 86400)

    try:
        peer_token_ttl = int(base.get("peer_token_ttl") or 120)
    except (TypeError, ValueError):
        peer_token_ttl = 120
    # Keep the token alive for at least two refresh windows.
    base["peer_token_ttl"] = min(max(peer_token_ttl, base["peer_token_refresh_interval"] * 2, 10), 86400)

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
    data = load_store()
    nodes = data.get("nodes", [])
    cleaned: list[dict[str, Any]] = []
    changed = False
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not is_valid_node_id(node.get("id")):
            continue
        normalized = normalize_node(node, existing=node)

        # One-time migration for older panel stores created before peer-token
        # verification was introduced. Without persisting this value, each
        # get_node/list_nodes call could generate a different transient secret:
        # the node would receive one secret in its applied routing config while
        # /api/node-peer-token could sign tokens with another one. In lab stacks
        # this shows up as peer runtime sync 401 / PEER_SECRET_MISSING or bad
        # peer token signature after reinstalling or reusing old data/lab stores.
        if not str(node.get("peer_verify_secret") or "").strip() and str(normalized.get("peer_verify_secret") or "").strip():
            migrated = dict(node)
            migrated["peer_verify_secret"] = normalized["peer_verify_secret"]
            migrated["peer_token_refresh_interval"] = normalized.get("peer_token_refresh_interval", 30)
            migrated["peer_token_ttl"] = normalized.get("peer_token_ttl", 120)
            migrated["updated_at"] = normalized.get("updated_at")
            nodes[index] = migrated
            changed = True
            normalized = normalize_node(migrated, existing=migrated)

        cleaned.append(normalized)
    if changed:
        data["version"] = 4
        save_store(data)
    return cleaned


def get_node(node_id: str) -> Optional[dict[str, Any]]:
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
    data["version"] = 4
    save_store(data)
    return node


def update_node(node_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not is_valid_node_id(node_id):
        return None
    data = load_store()
    nodes = data.setdefault("nodes", [])
    for index, node in enumerate(nodes):
        if node.get("id") == node_id:
            payload = dict(payload)
            payload["id"] = node_id
            nodes[index] = normalize_node(payload, existing=node)
            data["version"] = 4
            save_store(data)
            return nodes[index]
    return None


def set_node_check_result(node_id: str, *, ok: bool, error: str = "", details: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
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
            data["version"] = 4
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
    data["version"] = 4
    save_store(data)
    return True







