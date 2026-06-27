from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_CORE_STATUSES = {"draft", "ready", "applied", "error", "disabled"}
VALID_BALANCER_STRATEGIES = {"round_robin", "random", "failover", "least_connections"}
VALID_TARGET_TYPES = {"static", "balancer"}
VALID_ENDPOINT_TYPES = {"static", "node_inbound"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_cores_path() -> Path:
    configured = os.getenv("DOCTOR_DEV_CORES_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_dir = Path(os.getenv("DOCTOR_DEV_DATA_DIR", "/var/lib/doctor-dev-panel")).expanduser()
    if os.access(str(data_dir.parent), os.W_OK) or data_dir.exists():
        return data_dir / "cores.json"
    return Path.cwd() / "data" / "cores.json"


def cores_path() -> Path:
    return default_cores_path().resolve()


def generate_core_id() -> str:
    return "core_" + secrets.token_hex(8)


def empty_store() -> dict[str, Any]:
    return {"version": 1, "cores": []}


def load_store() -> dict[str, Any]:
    path = cores_path()
    if not path.exists():
        return empty_store()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Cannot read cores store: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        return empty_store()
    loaded.setdefault("version", 1)
    if not isinstance(loaded.get("cores"), list):
        loaded["cores"] = []
    return loaded


def save_store(data: dict[str, Any]) -> None:
    path = cores_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="cores.", suffix=".tmp", dir=str(path.parent))
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


def _clean_name(value: Any, default: str = "") -> str:
    return str(value or default).strip()


def _port_list(value: Any) -> list[int]:
    if value is None or value == "":
        return []
    raw: list[Any]
    if isinstance(value, str):
        raw = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        raw = value
    else:
        raw = [value]
    ports: list[int] = []
    for item in raw:
        try:
            port = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return ports


def normalize_inbound(payload: dict[str, Any], index: int = 0) -> dict[str, Any]:
    port_mode = _clean_name(payload.get("port_mode"), "fixed").lower()
    if port_mode not in {"fixed", "random"}:
        port_mode = "fixed"
    target_type = _clean_name(payload.get("target_type"), "static").lower()
    if target_type not in VALID_TARGET_TYPES:
        target_type = "static"
    name = _clean_name(payload.get("name"), f"inbound-{index + 1}")
    fixed_ports = _port_list(payload.get("fixed_ports"))
    random_count = int(payload.get("random_count") or 1)
    random_count = max(1, min(random_count, 4096))
    target_port = payload.get("target_port")
    try:
        target_port_int = int(target_port) if target_port not in {None, ""} else None
    except (TypeError, ValueError):
        target_port_int = None
    if target_port_int is not None and not 1 <= target_port_int <= 65535:
        target_port_int = None
    return {
        "name": name,
        "bind_ip": _clean_name(payload.get("bind_ip"), "0.0.0.0"),
        "public_host": _clean_name(payload.get("public_host"), ""),
        "port_mode": port_mode,
        "fixed_ports": fixed_ports,
        "random_count": random_count,
        "target_type": target_type,
        "target_host": _clean_name(payload.get("target_host"), "127.0.0.1"),
        "target_port": target_port_int or 80,
        "target_balancer": _clean_name(payload.get("target_balancer"), ""),
        "certificate": str(payload.get("certificate") or ""),
        "enabled": bool(payload.get("enabled", True)),
        "notes": _clean_name(payload.get("notes"), ""),
    }


def normalize_endpoint(payload: dict[str, Any], index: int = 0) -> dict[str, Any]:
    endpoint_type = _clean_name(payload.get("type"), payload.get("endpoint_type") or "static").lower()
    if endpoint_type not in VALID_ENDPOINT_TYPES:
        endpoint_type = "static"
    raw_port = payload.get("port")
    try:
        port = int(raw_port) if raw_port not in {None, ""} else 80
    except (TypeError, ValueError):
        port = 80
    if not 1 <= port <= 65535:
        port = 80
    weight = payload.get("weight")
    try:
        weight_num = float(weight) if weight not in {None, ""} else 1
    except (TypeError, ValueError):
        weight_num = 1
    return {
        "type": endpoint_type,
        "host": _clean_name(payload.get("host"), "127.0.0.1"),
        "port": port,
        "node_id": _clean_name(payload.get("node_id"), ""),
        "core_id": _clean_name(payload.get("core_id"), ""),
        "inbound_name": _clean_name(payload.get("inbound_name"), ""),
        "weight": max(0, weight_num),
        "certificate": str(payload.get("certificate") or ""),
        "enabled": bool(payload.get("enabled", True)),
        "notes": _clean_name(payload.get("notes"), ""),
    }


def normalize_balancer(payload: dict[str, Any], index: int = 0) -> dict[str, Any]:
    alias = _clean_name(payload.get("alias"), f"balancer-{index + 1}")
    strategy = _clean_name(payload.get("strategy"), "round_robin").lower()
    if strategy not in VALID_BALANCER_STRATEGIES:
        strategy = "round_robin"
    endpoints_payload = payload.get("endpoints")
    if not isinstance(endpoints_payload, list):
        endpoints_payload = []
    return {
        "alias": alias,
        "strategy": strategy,
        "endpoints": [normalize_endpoint(endpoint, idx) for idx, endpoint in enumerate(endpoints_payload)],
        "enabled": bool(payload.get("enabled", True)),
        "notes": _clean_name(payload.get("notes"), ""),
    }


def normalize_core(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now()
    base = dict(existing or {})
    base.update(payload)
    base.setdefault("id", generate_core_id())
    base.setdefault("created_at", now)
    base["updated_at"] = now
    base["name"] = _clean_name(base.get("name"), "core")
    base["node_id"] = _clean_name(base.get("node_id"), "")
    base["enabled"] = bool(base.get("enabled", True))
    status = _clean_name(base.get("status"), "ready").lower()
    base["status"] = "disabled" if not base["enabled"] else (status if status in VALID_CORE_STATUSES and status != "disabled" else "ready")
    inbounds_payload = base.get("inbounds")
    if not isinstance(inbounds_payload, list):
        inbounds_payload = []
    balancers_payload = base.get("balancers")
    if not isinstance(balancers_payload, list):
        balancers_payload = []
    base["inbounds"] = [normalize_inbound(item, idx) for idx, item in enumerate(inbounds_payload)]
    base["balancers"] = [normalize_balancer(item, idx) for idx, item in enumerate(balancers_payload)]
    base.setdefault("last_applied_at", None)
    base.setdefault("last_error", "")
    return base


def list_cores() -> list[dict[str, Any]]:
    return [normalize_core(core, existing=core) for core in load_store().get("cores", [])]


def get_core(core_id: str) -> dict[str, Any] | None:
    for core in list_cores():
        if core.get("id") == core_id:
            return core
    return None


def create_core(payload: dict[str, Any]) -> dict[str, Any]:
    data = load_store()
    core = normalize_core(payload)
    data.setdefault("cores", []).append(core)
    data["version"] = 1
    save_store(data)
    return core


def update_core(core_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    data = load_store()
    cores = data.setdefault("cores", [])
    for index, core in enumerate(cores):
        if core.get("id") == core_id:
            payload = dict(payload)
            payload["id"] = core_id
            cores[index] = normalize_core(payload, existing=core)
            data["version"] = 1
            save_store(data)
            return cores[index]
    return None


def remove_core(core_id: str) -> bool:
    data = load_store()
    cores = data.setdefault("cores", [])
    next_cores = [core for core in cores if core.get("id") != core_id]
    if len(next_cores) == len(cores):
        return False
    data["cores"] = next_cores
    data["version"] = 1
    save_store(data)
    return True


def inbound_catalog(node_id: str | None = None) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for core in list_cores():
        if node_id and core.get("node_id") != node_id:
            continue
        for inbound in core.get("inbounds", []):
            ports = inbound.get("fixed_ports", []) if inbound.get("port_mode") == "fixed" else []
            catalog.append(
                {
                    "core_id": core.get("id"),
                    "core_name": core.get("name"),
                    "node_id": core.get("node_id"),
                    "inbound_name": inbound.get("name"),
                    "bind_ip": inbound.get("bind_ip"),
                    "public_host": inbound.get("public_host"),
                    "port_mode": inbound.get("port_mode"),
                    "ports": ports,
                    "random_count": inbound.get("random_count"),
                    "enabled": bool(core.get("enabled")) and bool(inbound.get("enabled")),
                    "certificate": inbound.get("certificate", ""),
                }
            )
    return catalog


def build_node_config(node_id: str) -> dict[str, Any]:
    """Return a normalized node-side routing config preview.

    This is intentionally a lightweight data-plane config. The high-performance
    forwarding runtime will consume this shape in the next implementation step.
    """
    cores = [core for core in list_cores() if core.get("node_id") == node_id]
    return {
        "version": 1,
        "node_id": node_id,
        "generated_at": _now(),
        "cores": cores,
    }
