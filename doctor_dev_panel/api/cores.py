from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..api_errors import api_error
from ..auth import require_admin
from ..core_store import (
    build_node_config,
    create_core,
    get_core,
    inbound_catalog,
    list_cores,
    remove_core,
    set_core_apply_result,
    update_core,
)
from ..deps import pydantic_to_dict, require_core_id, validate_manual_json_config
from ..id_utils import is_valid_node_id
from ..node_runtime_cache import get_node_runtime
from ..node_store import get_node
from ..schemas import AdvancedConfigValidateBody, CoreBody
from ..services.node_control import NodeAPIError, post_node_api
from ..services.runtime_sync import sync_node_runtime_once

logger = logging.getLogger("doctor_dev_panel.api.cores")
router = APIRouter()


def _validate_core_forwarding_topology(body: CoreBody) -> None:
    local_hosts = {"", "127.0.0.1", "localhost", "::1", "0.0.0.0", "[::1]"}
    balancers = {b.alias: b for b in body.balancers if b.enabled}
    errors: list[str] = []

    def local_self(host: str, port: int, inbound) -> bool:
        fixed = set(int(p) for p in inbound.fixed_ports or [])
        if port not in fixed:
            return False
        host_l = str(host or "").strip().lower()
        bind_l = str(inbound.bind_ip or "0.0.0.0").strip().lower()
        public_l = str(inbound.public_host or "").strip().lower()
        return host_l in local_hosts or host_l == bind_l or (public_l and host_l == public_l)

    for inbound in body.inbounds:
        if not inbound.enabled:
            continue
        if inbound.port_mode == "fixed" and not inbound.fixed_ports:
            errors.append(f"{inbound.name}: choose at least one listen port.")
        if inbound.target_type == "static":
            if local_self(inbound.target_host, int(inbound.target_port), inbound):
                errors.append(
                    f"{inbound.name}: target points back to the same inbound port. "
                    "Use the real upstream host/port, not the listen port."
                )
        elif inbound.target_type == "balancer":
            balancer = balancers.get(inbound.target_balancer)
            if not balancer:
                errors.append(f"{inbound.name}: selected balancer does not exist or is disabled.")
                continue
            enabled_endpoints = [e for e in balancer.endpoints if e.enabled]
            if not enabled_endpoints:
                errors.append(f"{inbound.name}: selected balancer has no enabled endpoint.")
            for endpoint in enabled_endpoints:
                if endpoint.type == "static" and local_self(endpoint.host, int(endpoint.port), inbound):
                    errors.append(
                        f"{inbound.name}: balancer endpoint {endpoint.host}:{endpoint.port} "
                        "points back to this inbound listener."
                    )
    if errors:
        raise api_error(400, "INVALID_FORWARDING_TOPOLOGY", " | ".join(errors[:6]))


def _validate_core_advanced_config(body: CoreBody) -> None:
    adv = body.advanced_config
    if not adv or not adv.enabled:
        return
    result = validate_manual_json_config(adv.json_config)
    if not result.get("valid"):
        message = "; ".join(result.get("errors") or ["Advanced JSON is invalid."])
        raise api_error(400, "INVALID_ADVANCED_JSON", message)


def _ensure_single_enabled_core_per_node(node_id: str, *, current_core_id: str = "") -> None:
    for core in list_cores():
        if str(core.get("node_id") or "") != str(node_id):
            continue
        if current_core_id and str(core.get("id") or "") == str(current_core_id):
            continue
        if core.get("enabled") is not False:
            raise api_error(
                409,
                "NODE_ALREADY_HAS_CORE",
                "Each node can have only one enabled core. Disable or move the existing core before adding another one.",
            )


@router.get("/api/cores")
async def api_list_cores(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "cores": list_cores(), "inbound_catalog": inbound_catalog()}


@router.post("/api/cores/advanced/validate")
async def api_validate_advanced_config(body: AdvancedConfigValidateBody, user: str = Depends(require_admin)) -> dict:
    result = validate_manual_json_config(body.json_config)
    return {"ok": True, **result}


@router.post("/api/cores")
async def api_create_core(body: CoreBody, user: str = Depends(require_admin)) -> dict:
    if not is_valid_node_id(body.node_id):
        raise api_error(400, "INVALID_NODE_ID", "Select a valid node before creating a core.")
    if not get_node(body.node_id):
        raise api_error(400, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    if body.enabled:
        _ensure_single_enabled_core_per_node(body.node_id)
    _validate_core_advanced_config(body)
    _validate_core_forwarding_topology(body)
    core = create_core(pydantic_to_dict(body))
    logger.info("core created: id=%s name=%s node_id=%s by=%s", core.get("id"), core.get("name"), core.get("node_id"), user)
    return {"ok": True, "core": core}


@router.put("/api/cores/{core_id}")
async def api_update_core(core_id: str, body: CoreBody, user: str = Depends(require_admin)) -> dict:
    core_id = require_core_id(core_id)
    if not is_valid_node_id(body.node_id):
        raise api_error(400, "INVALID_NODE_ID", "Select a valid node before saving this core.")
    if not get_node(body.node_id):
        raise api_error(400, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    if body.enabled:
        _ensure_single_enabled_core_per_node(body.node_id, current_core_id=core_id)
    _validate_core_advanced_config(body)
    _validate_core_forwarding_topology(body)
    core = update_core(core_id, pydantic_to_dict(body))
    if not core:
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
    logger.info("core updated: id=%s name=%s node_id=%s by=%s", core.get("id"), core.get("name"), core.get("node_id"), user)
    return {"ok": True, "core": core}


@router.delete("/api/cores/{core_id}")
async def api_delete_core(core_id: str, user: str = Depends(require_admin)) -> dict:
    core_id = require_core_id(core_id)
    if not remove_core(core_id):
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
    logger.info("core deleted: id=%s by=%s", core_id, user)
    return {"ok": True}


@router.get("/api/cores/{core_id}/preview")
async def api_core_preview(core_id: str, user: str = Depends(require_admin)) -> dict:
    core_id = require_core_id(core_id)
    core = get_core(core_id)
    if not core:
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
    return {"ok": True, "core": core, "node_config_preview": build_node_config(str(core.get("node_id")))}


@router.post("/api/cores/{core_id}/apply")
async def api_apply_core(core_id: str, user: str = Depends(require_admin)) -> dict:
    core_id = require_core_id(core_id)
    core = get_core(core_id)
    if not core:
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
    node_id = str(core.get("node_id") or "")
    node = get_node(node_id)
    if not node:
        set_core_apply_result(core_id, ok=False, error="Selected node does not exist.")
        raise api_error(400, "NODE_NOT_FOUND", "The node linked to this core no longer exists. Run Repair Data or select another node.")
    payload = build_node_config(node_id)
    try:
        data = await asyncio.to_thread(post_node_api, node, "/config/apply", payload)
        updated = set_core_apply_result(core_id, ok=True)
        await sync_node_runtime_once(node)
        runtime_entry = get_node_runtime(node_id)
        logger.info("core applied: core_id=%s node_id=%s by=%s", core_id, node_id, user)
        return {"ok": True, "message": "Core configuration was applied successfully.", "core": updated, "node_response": data, "runtime": runtime_entry}
    except NodeAPIError as exc:
        updated = set_core_apply_result(core_id, ok=False, error=str(exc))
        logger.warning("core apply failed: core_id=%s node_id=%s error=%s", core_id, node_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
