
from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .node_runtime_cache import find_live_inbound_ports, get_node_runtime

from .id_utils import is_valid_core_id, is_valid_node_id

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


def normalize_dependency(payload: dict[str, Any], index: int = 0) -> dict[str, Any]:
    dep_type = _clean_name(payload.get("type"), "core").lower()
    if dep_type not in {"core", "node"}:
        dep_type = "core"
    try:
        sync_interval = int(payload.get("sync_interval") or payload.get("update_interval") or 5)
    except (TypeError, ValueError):
        sync_interval = 5
    return {
        "type": dep_type,
        "ref_id": _clean_name(payload.get("ref_id"), ""),
        "sync_interval": min(max(sync_interval, 1), 86400),
        "required": bool(payload.get("required", True)),
        "notes": _clean_name(payload.get("notes"), ""),
    }


def normalize_advanced_config(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    raw = payload.get("json_config", "")
    if raw is None:
        raw = ""
    if not isinstance(raw, str):
        try:
            raw = json.dumps(raw, ensure_ascii=False, indent=2)
        except TypeError:
            raw = ""
    return {
        "enabled": bool(payload.get("enabled", False)),
        "json_config": raw[:200000],
    }


def normalize_core(payload: dict[str, Any], existing: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    now = _now()
    base = dict(existing or {})
    base.update(payload)
    if not is_valid_core_id(base.get("id")):
        base["id"] = generate_core_id()
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
    dependencies_payload = base.get("dependencies")
    if not isinstance(dependencies_payload, list):
        dependencies_payload = []
    base["inbounds"] = [normalize_inbound(item, idx) for idx, item in enumerate(inbounds_payload)]
    base["balancers"] = [normalize_balancer(item, idx) for idx, item in enumerate(balancers_payload)]
    dependencies = [normalize_dependency(item, idx) for idx, item in enumerate(dependencies_payload)]
    # A node dependency must point to a different node. Keeping a self-node
    # dependency is misleading in the UI and cannot produce peer-sync metadata.
    base["dependencies"] = [
        dep for dep in dependencies
        if not (dep.get("type") == "node" and str(dep.get("ref_id") or "") == str(base.get("node_id") or ""))
    ]
    base["advanced_config"] = normalize_advanced_config(base.get("advanced_config"))
    base.setdefault("last_applied_at", None)
    base.setdefault("last_error", "")
    return base


def list_cores() -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for core in load_store().get("cores", []):
        if not isinstance(core, dict) or not is_valid_core_id(core.get("id")):
            continue
        cleaned.append(normalize_core(core, existing=core))
    return cleaned


def get_core(core_id: str) -> Optional[dict[str, Any]]:
    if not is_valid_core_id(core_id):
        return None
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


def update_core(core_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not is_valid_core_id(core_id):
        return None
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
    if not is_valid_core_id(core_id):
        return False
    data = load_store()
    cores = data.setdefault("cores", [])
    next_cores = [core for core in cores if core.get("id") != core_id]
    if len(next_cores) == len(cores):
        return False
    data["cores"] = next_cores
    data["version"] = 1
    save_store(data)
    return True


def inbound_catalog(node_id: Optional[str] = None) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for core in list_cores():
        if node_id and core.get("node_id") != node_id:
            continue
        for inbound in core.get("inbounds", []):
            is_random = inbound.get("port_mode") == "random"
            ports = inbound.get("fixed_ports", []) if not is_random else []
            random_count = inbound.get("random_count") or 1
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
                    "random_count": random_count,
                    "ports_summary": f"random ×{random_count}" if is_random else ",".join(str(p) for p in ports),
                    "enabled": bool(core.get("enabled")) and bool(inbound.get("enabled")),
                }
            )
    return catalog


def _address_host(address: Any) -> str:
    raw = str(address or "").strip()
    if not raw:
        return "127.0.0.1"
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname or raw.split("/", 1)[0].split(":", 1)[0]
    return host.strip() or "127.0.0.1"




def _node_sync_urls(node: dict[str, Any]) -> list[str]:
    raw = str(node.get("address") or "").strip()
    if not raw:
        return []
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.netloc or parsed.path
    host = host.split("/", 1)[0].strip()
    if not host:
        return []
    if ":" in host and not host.startswith("[") and host.count(":") == 1:
        host = host.split(":", 1)[0]
    try:
        api_port = int(node.get("api_port") or 62051)
    except (TypeError, ValueError):
        api_port = 62051
    if "://" in raw and parsed.scheme:
        schemes = [parsed.scheme]
    else:
        schemes = ["http"]
    urls: list[str] = []
    for scheme in schemes:
        for path in ("/runtime", "/config/export"):
            url = f"{scheme}://{host}:{api_port}{path}"
            if url not in urls:
                urls.append(url)
    return urls


def _dependency_sync_interval(dep: dict[str, Any]) -> int:
    """Return the node-to-node runtime sync interval carried by a dependency.

    The interval is intentionally dependency-scoped, not node-scoped. A core on
    node B can depend on node A every 3 seconds while another core/dependency
    uses a slower cadence. Legacy configs that still contain update_interval are
    accepted as a fallback, but new UI/API writes sync_interval only.
    """
    try:
        interval = int(dep.get("sync_interval") or dep.get("update_interval") or 5)
    except (TypeError, ValueError):
        interval = 5
    return min(max(interval, 1), 86400)


def _dependency_interval_map(core: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    dependencies = core.get("dependencies") if isinstance(core.get("dependencies"), list) else []
    for dep in dependencies:
        if not isinstance(dep, dict) or dep.get("type") != "node" or dep.get("required") is False:
            continue
        ref_id = str(dep.get("ref_id") or "").strip()
        if ref_id:
            result[ref_id] = _dependency_sync_interval(dep)
    return result


def _first_enabled_core_for_node(node_id: str, cores: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for core in cores:
        if not isinstance(core, dict):
            continue
        if str(core.get("node_id") or "") == str(node_id) and core.get("enabled") is not False:
            return core
    for core in cores:
        if not isinstance(core, dict):
            continue
        if str(core.get("node_id") or "") == str(node_id):
            return core
    return None


def _peer_token_url() -> str:
    scheme = os.getenv("PUBLIC_SCHEME", "http").strip() or "http"
    host = os.getenv("PUBLIC_HOST", os.getenv("HOST", "127.0.0.1")).strip() or "127.0.0.1"
    port = str(os.getenv("PORT", "8080")).strip()
    default_port = (scheme == "http" and port == "80") or (scheme == "https" and port == "443")
    return f"{scheme}://{host}{'' if default_port else ':' + port}/api/node-peer-token"


def _node_peer_token_refresh_interval(node: dict[str, Any]) -> int:
    try:
        interval = int(node.get("peer_token_refresh_interval") or 30)
    except (TypeError, ValueError):
        interval = 30
    return min(max(interval, 5), 86400)


def _attach_peer_sync_fields(endpoint: dict[str, Any], target_node: dict[str, Any], target_node_id: str, target_core_id: str, inbound_name: str, sync_interval: int = 5) -> None:
    endpoint["remote_node_id"] = target_node_id
    endpoint["remote_core_id"] = target_core_id
    endpoint["remote_inbound_name"] = inbound_name
    endpoint["sync_urls"] = _node_sync_urls(target_node)
    endpoint["token_url"] = _peer_token_url()
    endpoint["token_refresh_interval"] = _node_peer_token_refresh_interval(target_node)
    endpoint.pop("update_interval", None)
    endpoint["sync_interval"] = min(max(int(sync_interval or 5), 1), 86400)
    endpoint["api_port"] = int(target_node.get("api_port") or 62051)
    endpoint["peer_host"] = _address_host(target_node.get("address"))



def _iso_to_unix(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return 0.0


def _fixed_ports(inbound: dict[str, Any]) -> list[int]:
    ports: list[int] = []
    for item in inbound.get("fixed_ports") or []:
        try:
            port = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return ports

def _first_fixed_port(inbound: dict[str, Any]) -> Optional[int]:
    for item in inbound.get("fixed_ports") or []:
        try:
            port = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535:
            return port
    return None


def _enrich_node_inbound_endpoints(config_node_id: str, cores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve Node Inbound endpoint references into usable host/port data.

    The UI stores semantic references (`node_id`, `core_id`, `inbound_name`).
    The node runtime only receives the config for the node being applied, so
    references to remote nodes must be enriched with the remote node host and
    selected inbound port here. Same-node references can still be resolved by
    the runtime, but we also attach the first fixed port for diagnostics.
    """
    try:
        from .node_store import list_nodes
    except Exception:  # pragma: no cover - defensive fallback
        list_nodes = lambda: []  # type: ignore[assignment]

    all_cores = list_cores()
    node_map = {str(node.get("id")): node for node in list_nodes() if isinstance(node, dict)}

    def find_inbound(target_node_id: str, core_id: str, inbound_name: str) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        for core in all_cores:
            if target_node_id and str(core.get("node_id") or "") != target_node_id:
                continue
            if core_id and str(core.get("id") or "") != core_id:
                continue
            for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                if inbound_name and str(inbound.get("name") or "") != inbound_name:
                    continue
                return core, inbound
        return None, None

    for core in cores:
        dependency_intervals = _dependency_interval_map(core)
        for balancer in core.get("balancers", []) if isinstance(core.get("balancers"), list) else []:
            endpoints = balancer.get("endpoints") if isinstance(balancer.get("endpoints"), list) else []
            for endpoint in endpoints:
                if not isinstance(endpoint, dict) or endpoint.get("type") != "node_inbound":
                    continue
                target_node_id = str(endpoint.get("node_id") or config_node_id)
                inbound_name = str(endpoint.get("inbound_name") or "")
                core_id = str(endpoint.get("core_id") or "")
                target_core, target_inbound = find_inbound(target_node_id, core_id, inbound_name)
                if not target_inbound:
                    endpoint["resolve_error"] = "Selected node inbound was not found."
                    continue
                target_core_id = str(target_core.get("id") or core_id or "") if target_core else core_id
                endpoint["core_id"] = target_core_id
                endpoint["inbound_name"] = str(target_inbound.get("name") or inbound_name)
                target_node = node_map.get(target_node_id, {})
                _attach_peer_sync_fields(endpoint, target_node, target_node_id, target_core_id, str(endpoint.get("inbound_name") or ""), dependency_intervals.get(target_node_id, 5))
                endpoint["remote_port_mode"] = str(target_inbound.get("port_mode") or "fixed")
                endpoint["remote_random_count"] = int(target_inbound.get("random_count") or 1)

                host = "127.0.0.1" if target_node_id == config_node_id else str(target_inbound.get("public_host") or _address_host(target_node.get("address")))
                endpoint["host"] = host
                runtime_entry = get_node_runtime(target_node_id) or {}
                endpoint["live_ports_synced_at"] = runtime_entry.get("last_success_at") or runtime_entry.get("synced_at") or ""
                endpoint["live_ports_synced_at_unix"] = _iso_to_unix(endpoint.get("live_ports_synced_at"))

                live_ports = find_live_inbound_ports(target_node_id, target_core_id, str(endpoint.get("inbound_name") or ""))
                if live_ports:
                    endpoint["port"] = live_ports[0]
                    endpoint["resolved_from"] = "node_inbound_live_cache"
                    endpoint["live_ports"] = live_ports[:256]
                    continue

                fixed_ports = _fixed_ports(target_inbound)
                if fixed_ports:
                    endpoint["port"] = fixed_ports[0]
                    endpoint["resolved_from"] = "node_inbound_fixed"
                    endpoint["live_ports"] = fixed_ports[:256]
                    endpoint["live_ports_synced_at"] = ""
                    endpoint["live_ports_synced_at_unix"] = 0
                    continue

                if target_inbound.get("port_mode") == "random":
                    # Same-node random inbounds are resolved directly from the active listener table.
                    # Remote random inbounds must be resolved by node-side peer sync using
                    # sync_urls + peer tokens. Never use random_count as a TCP port and
                    # never fall back to a placeholder port for remote random inbounds.
                    endpoint["port"] = 80
                    endpoint["live_ports"] = []
                    endpoint["resolved_from"] = "node_inbound_random_peer_sync" if target_node_id != config_node_id else "node_inbound_random_runtime"
                    continue

                endpoint["resolve_error"] = "Selected node inbound has no fixed or live port."
    return cores


def _enrich_node_dependencies(config_node_id: str, cores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach peer sync credentials for node dependencies.

    A core can depend on another node even if a balancer endpoint also carries
    a node-inbound reference. Sending the peer token and sync URLs with the
    applied config lets the running node keep the dependency node's live runtime
    state fresh without another manual apply.
    """
    try:
        from .node_store import list_nodes
    except Exception:  # pragma: no cover - defensive fallback
        list_nodes = lambda: []  # type: ignore[assignment]

    node_map = {str(node.get("id")): node for node in list_nodes() if isinstance(node, dict)}
    all_cores = list_cores()
    for core in cores:
        dependencies = core.get("dependencies") if isinstance(core.get("dependencies"), list) else []
        for dep in dependencies:
            if not isinstance(dep, dict) or dep.get("type") != "node":
                continue
            target_node_id = str(dep.get("ref_id") or "")
            if not target_node_id or target_node_id == config_node_id:
                continue
            target_node = node_map.get(target_node_id)
            if not target_node:
                dep["resolve_error"] = "Selected dependency node was not found."
                continue
            target_core = _first_enabled_core_for_node(target_node_id, all_cores)
            if not target_core:
                dep["resolve_error"] = "Selected dependency node has no core to export."
                continue
            dep_interval = _dependency_sync_interval(dep)
            dep["remote_node_id"] = target_node_id
            dep["remote_core_id"] = str(target_core.get("id") or "")
            dep["sync_urls"] = _node_sync_urls(target_node)
            dep["token_url"] = _peer_token_url()
            dep["token_refresh_interval"] = _node_peer_token_refresh_interval(target_node)
            dep.pop("update_interval", None)
            dep["sync_interval"] = dep_interval
            dep["peer_host"] = _address_host(target_node.get("address"))
    return cores


def build_node_config(node_id: str) -> dict[str, Any]:
    """Return a normalized node-side routing config preview.

    This is intentionally a lightweight data-plane config. The high-performance
    forwarding runtime will consume this shape in the next implementation step.
    """
    if not is_valid_node_id(node_id):
        cores = []
    else:
        cores = [core for core in list_cores() if core.get("node_id") == node_id]
    cores = _enrich_node_inbound_endpoints(node_id, cores)
    cores = _enrich_node_dependencies(node_id, cores)
    for core in cores:
        adv = core.get("advanced_config") if isinstance(core.get("advanced_config"), dict) else {}
        raw = str(adv.get("json_config") or "").strip()
        if adv.get("enabled") and raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    core["manual_config"] = parsed
            except json.JSONDecodeError:
                core["manual_config_error"] = "Advanced JSON is not valid."
    try:
        from .node_store import get_node
        node = get_node(node_id) or {}
    except Exception:  # pragma: no cover
        node = {}
    return {
        "version": 1,
        "node_id": node_id,
        "generated_at": _now(),
        "peer_verify_secret": str(node.get("peer_verify_secret") or ""),
        "cores": cores,
    }


def set_core_apply_result(core_id: str, *, ok: bool, error: str = "") -> Optional[dict[str, Any]]:
    if not is_valid_core_id(core_id):
        return None
    data = load_store()
    cores = data.setdefault("cores", [])
    for index, core in enumerate(cores):
        if core.get("id") == core_id:
            updated = normalize_core(core, existing=core)
            updated["status"] = "applied" if ok and updated.get("enabled", True) else ("error" if not ok else "disabled")
            updated["last_applied_at"] = _now() if ok else updated.get("last_applied_at")
            updated["last_error"] = "" if ok else str(error or "Unknown apply error")[:500]
            cores[index] = updated
            data["version"] = 1
            save_store(data)
            return updated
    return None


def set_node_cores_apply_result(node_id: str, *, ok: bool, error: str = "") -> list[dict[str, Any]]:
    if not is_valid_node_id(node_id):
        return []
    data = load_store()
    cores = data.setdefault("cores", [])
    changed: list[dict[str, Any]] = []
    now = _now()
    for index, core in enumerate(cores):
        if core.get("node_id") == node_id:
            updated = normalize_core(core, existing=core)
            updated["status"] = "applied" if ok and updated.get("enabled", True) else ("error" if not ok else "disabled")
            if ok:
                updated["last_applied_at"] = now
                updated["last_error"] = ""
            else:
                updated["last_error"] = str(error or "Unknown apply error")[:500]
            cores[index] = updated
            changed.append(updated)
    if changed:
        data["version"] = 1
        save_store(data)
    return changed


def disable_cores_for_node(node_id: str, *, error: str = "Linked node was removed.") -> list[dict[str, Any]]:
    if not is_valid_node_id(node_id):
        return []
    data = load_store()
    cores = data.setdefault("cores", [])
    changed: list[dict[str, Any]] = []
    for index, core in enumerate(cores):
        if isinstance(core, dict) and core.get("node_id") == node_id and is_valid_core_id(core.get("id")):
            updated = normalize_core(core, existing=core)
            updated["enabled"] = False
            updated["status"] = "disabled"
            updated["last_error"] = error[:500]
            updated["updated_at"] = _now()
            cores[index] = updated
            changed.append(updated)
    if changed:
        data["version"] = 1
        save_store(data)
    return changed







