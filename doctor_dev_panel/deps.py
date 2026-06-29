from __future__ import annotations

import json
from typing import Any

from .api_errors import api_error
from .id_utils import is_valid_core_id, is_valid_node_id


def pydantic_to_dict(model: object) -> dict[str, Any]:
    """Return a plain dict from Pydantic v1 or v2 models."""
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    if hasattr(model, "dict"):
        return model.dict()  # type: ignore[attr-defined]
    return dict(model)  # type: ignore[arg-type]


def require_node_id(node_id: str) -> str:
    if not is_valid_node_id(node_id):
        raise api_error(400, "INVALID_NODE_ID", "Invalid node identifier. Refresh the page and try again.")
    return node_id


def require_core_id(core_id: str) -> str:
    if not is_valid_core_id(core_id):
        raise api_error(400, "INVALID_CORE_ID", "Invalid core identifier. Refresh the page and try again.")
    return core_id


def _json_depth(value: object, depth: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return depth + 1
        return max(_json_depth(v, depth + 1) for v in value.values())
    if isinstance(value, list):
        if not value:
            return depth + 1
        return max(_json_depth(v, depth + 1) for v in value)
    return depth + 1


def _walk_json(value: object, path: str = "$") -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            items.extend(_walk_json(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(_walk_json(child, f"{path}[{index}]"))
    return items


def validate_manual_json_config(raw: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    text = (raw or "").strip()
    if not text:
        return {"valid": True, "errors": [], "warnings": ["Manual JSON is empty."], "normalized": None}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "errors": [f"Invalid JSON syntax at line {exc.lineno}, column {exc.colno}: {exc.msg}."],
            "warnings": [],
            "normalized": None,
        }
    if not isinstance(parsed, dict):
        errors.append("JSON root must be an object.")
        return {"valid": False, "errors": errors, "warnings": warnings, "normalized": None}

    depth = _json_depth(parsed)
    if depth > 64:
        errors.append("JSON is too deeply nested. Maximum supported depth is 64 levels.")

    if "inbounds" in parsed and not isinstance(parsed.get("inbounds"), list):
        errors.append("Field 'inbounds' must be an array.")
    if "outbounds" in parsed and not isinstance(parsed.get("outbounds"), list):
        errors.append("Field 'outbounds' must be an array.")
    if "routing" in parsed and not isinstance(parsed.get("routing"), dict):
        errors.append("Field 'routing' must be an object.")

    seen_inbound_keys: set[tuple[str, int]] = set()
    inbounds = parsed.get("inbounds") if isinstance(parsed.get("inbounds"), list) else []
    for index, inbound in enumerate(inbounds):
        if not isinstance(inbound, dict):
            errors.append(f"inbounds[{index}] must be an object.")
            continue
        port = inbound.get("port")
        listen = str(inbound.get("listen") or "0.0.0.0")
        if port is None:
            warnings.append(f"inbounds[{index}] has no port field.")
        else:
            try:
                port_num = int(port)
                if not 1 <= port_num <= 65535:
                    errors.append(f"inbounds[{index}].port must be between 1 and 65535.")
                key = (listen, port_num)
                if key in seen_inbound_keys:
                    errors.append(f"Duplicate inbound listener {listen}:{port_num}.")
                seen_inbound_keys.add(key)
            except (TypeError, ValueError):
                errors.append(f"inbounds[{index}].port must be a number.")
        if not inbound.get("protocol"):
            warnings.append(f"inbounds[{index}] has no protocol field.")

    port_like_names = {"port", "target_port", "api_port", "listen_port"}
    for path, value in _walk_json(parsed):
        last = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if last in port_like_names and value not in (None, ""):
            try:
                port_num = int(value)
            except (TypeError, ValueError):
                errors.append(f"{path} must be a numeric port.")
                continue
            if not 1 <= port_num <= 65535:
                errors.append(f"{path} must be between 1 and 65535.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized": parsed if not errors else None,
    }
