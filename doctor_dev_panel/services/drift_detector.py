
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _enabled_desired_cores(desired_config: dict[str, Any]) -> list[dict[str, Any]]:
    cores = desired_config.get("cores") if isinstance(desired_config.get("cores"), list) else []
    return [core for core in cores if isinstance(core, dict) and core.get("enabled") is not False]


def _desired_inbounds(desired_config: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for core in _enabled_desired_cores(desired_config):
        for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
            if not isinstance(inbound, dict) or inbound.get("enabled") is False:
                continue
            result.append({
                "core_id": str(core.get("id") or ""),
                "core_name": str(core.get("name") or ""),
                "inbound_name": str(inbound.get("name") or ""),
                "port_mode": str(inbound.get("port_mode") or "fixed"),
                "fixed_ports": [int(p) for p in inbound.get("fixed_ports", []) if str(p).isdigit()],
                "target_type": str(inbound.get("target_type") or "static"),
                "target_balancer": str(inbound.get("target_balancer") or ""),
            })
    return result


def _runtime_listeners(runtime_entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(runtime_entry, dict):
        return []
    listeners = runtime_entry.get("listeners")
    if not isinstance(listeners, list):
        summary = runtime_entry.get("summary") if isinstance(runtime_entry.get("summary"), dict) else {}
        listeners = summary.get("listeners") if isinstance(summary.get("listeners"), list) else []
    return [item for item in listeners if isinstance(item, dict)]


def _listener_key(listener: dict[str, Any]) -> tuple[str, str]:
    return (str(listener.get("core_id") or ""), str(listener.get("inbound_name") or ""))


def _desired_key(inbound: dict[str, Any]) -> tuple[str, str]:
    return (str(inbound.get("core_id") or ""), str(inbound.get("inbound_name") or ""))


def detect_node_drift(node_id: str, desired_config: dict[str, Any], runtime_entry: dict[str, Any] | None) -> dict[str, Any]:
    """Compare panel desired config with the latest cached node runtime.

    The result is intentionally conservative: missing runtime or failed auth is
    reported as drift because the panel cannot prove that actual == desired.
    """
    desired_cores = _enabled_desired_cores(desired_config)
    desired_inbounds = _desired_inbounds(desired_config)
    listeners = _runtime_listeners(runtime_entry)
    listening = [item for item in listeners if item.get("status") == "listening"]

    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if len(desired_cores) > 1:
        problems.append({"code": "DESIRED_MULTIPLE_ENABLED_CORES", "message": "Panel desired config has more than one enabled core for this node."})

    if not runtime_entry:
        problems.append({"code": "RUNTIME_MISSING", "message": "No runtime has been synced for this node yet."})
    else:
        if not runtime_entry.get("reachable", False):
            problems.append({"code": "NODE_UNREACHABLE", "message": runtime_entry.get("last_error") or "Node runtime is unreachable."})
        if runtime_entry.get("auth_ok") is False:
            problems.append({"code": "NODE_AUTH_FAILED", "message": runtime_entry.get("last_error") or "Node runtime auth failed."})
        if runtime_entry.get("runtime_ok") is False:
            problems.append({"code": "RUNTIME_NOT_OK", "message": runtime_entry.get("last_error") or "Node reported a runtime error."})

    desired_by_key = {_desired_key(item): item for item in desired_inbounds}
    listeners_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for listener in listening:
        listeners_by_key.setdefault(_listener_key(listener), []).append(listener)

    for key, desired in desired_by_key.items():
        actuals = listeners_by_key.get(key, [])
        if not actuals:
            problems.append({
                "code": "LISTENER_MISSING",
                "message": f"Inbound {desired.get('inbound_name')} is enabled in desired config but not listening in runtime.",
                "core_id": key[0],
                "inbound_name": key[1],
            })
            continue
        if desired.get("port_mode") == "fixed":
            fixed_ports = set(int(p) for p in desired.get("fixed_ports") or [])
            actual_ports: list[int] = []
            for item in actuals:
                try:
                    actual_ports.append(int(item.get("port") or item.get("requested_port") or 0))
                except (TypeError, ValueError):
                    pass
            unexpected = [p for p in actual_ports if p and fixed_ports and p not in fixed_ports]
            if unexpected:
                problems.append({
                    "code": "FIXED_PORT_MISMATCH",
                    "message": f"Inbound {desired.get('inbound_name')} listens on {unexpected}, outside desired fixed ports {sorted(fixed_ports)}.",
                    "core_id": key[0],
                    "inbound_name": key[1],
                    "actual_ports": actual_ports,
                    "desired_ports": sorted(fixed_ports),
                })

    for key, actuals in listeners_by_key.items():
        if key not in desired_by_key:
            warnings.append({
                "code": "EXTRA_RUNTIME_LISTENER",
                "message": f"Runtime has listener {key[1]} that is not present/enabled in desired config.",
                "core_id": key[0],
                "inbound_name": key[1],
                "ports": [item.get("port") for item in actuals],
            })

    status = "ok" if not problems else "drift"
    return {
        "ok": not problems,
        "status": status,
        "node_id": node_id,
        "checked_at": _now(),
        "desired": {
            "enabled_cores_total": len(desired_cores),
            "inbounds_total": len(desired_inbounds),
            "config_generated_at": desired_config.get("generated_at"),
        },
        "actual": {
            "runtime_present": bool(runtime_entry),
            "reachable": bool((runtime_entry or {}).get("reachable")),
            "auth_ok": (runtime_entry or {}).get("auth_ok"),
            "runtime_ok": (runtime_entry or {}).get("runtime_ok"),
            "last_success_at": (runtime_entry or {}).get("last_success_at"),
            "listeners_total": len(listeners),
            "listening_total": len(listening),
            "config_hash": (runtime_entry or {}).get("config_hash"),
            "core": (runtime_entry or {}).get("core") or {},
        },
        "problems": problems,
        "warnings": warnings,
    }



