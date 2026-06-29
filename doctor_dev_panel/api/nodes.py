from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from ..api_errors import api_error
from ..auth import require_admin
from ..core_store import build_node_config, disable_cores_for_node, inbound_catalog, set_node_cores_apply_result
from ..deps import pydantic_to_dict, require_core_id, require_node_id
from ..node_runtime_cache import get_node_runtime
from ..node_store import (
    create_node,
    generate_api_key,
    get_node,
    list_nodes,
    remove_node,
    set_node_check_result,
    update_node,
)
from ..peer_tokens import issue_peer_token
from ..schemas import NodeBody
from ..services.drift_detector import detect_node_drift
from ..services.node_control import NodeAPIError, check_node_payload, post_node_api
from ..services.runtime_sync import sync_all_node_runtime, sync_node_runtime_once
from ..core_store import get_core

logger = logging.getLogger("doctor_dev_panel.api.nodes")
router = APIRouter()


class NodePeerTokenBody(BaseModel):
    source_node_id: str
    source_core_id: str
    target_node_id: str
    target_core_id: str


@router.get("/api/nodes")
async def api_list_nodes(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "nodes": list_nodes()}


@router.post("/api/nodes")
async def api_create_node(body: NodeBody, user: str = Depends(require_admin)) -> dict:
    node = create_node(pydantic_to_dict(body))
    return {"ok": True, "node": node}


@router.put("/api/nodes/{node_id}")
async def api_update_node(node_id: str, body: NodeBody, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    node = update_node(node_id, pydantic_to_dict(body))
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    return {"ok": True, "node": node}


@router.delete("/api/nodes/{node_id}")
async def api_delete_node(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    if not remove_node(node_id):
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    disabled_cores = disable_cores_for_node(
        node_id,
        error="This core was disabled because its linked node was deleted.",
    )
    logger.warning("node deleted: node_id=%s by=%s disabled_cores=%s", node_id, user, len(disabled_cores))
    return {"ok": True, "disabled_cores": disabled_cores}


@router.post("/api/nodes/api-key")
async def api_generate_node_key(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "api_key": generate_api_key()}


@router.post("/api/node-peer-token")
async def api_issue_node_peer_token(
    body: NodePeerTokenBody,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    source_node_id = require_node_id(body.source_node_id)
    target_node_id = require_node_id(body.target_node_id)
    source_core_id = require_core_id(body.source_core_id)
    target_core_id = require_core_id(body.target_core_id)

    source_node = get_node(source_node_id)
    target_node = get_node(target_node_id)
    source_core = get_core(source_core_id)
    target_core = get_core(target_core_id)
    if not source_node or not target_node or not source_core or not target_core:
        raise api_error(404, "PEER_TOKEN_TARGET_NOT_FOUND", "Node or core was not found.")
    if str(source_core.get("node_id") or "") != source_node_id:
        raise api_error(403, "PEER_TOKEN_SOURCE_MISMATCH", "Source core does not belong to source node.")
    if str(target_core.get("node_id") or "") != target_node_id:
        raise api_error(403, "PEER_TOKEN_TARGET_MISMATCH", "Target core does not belong to target node.")
    if authorization != f"Bearer {source_node.get('api_key')}":
        raise api_error(401, "INVALID_NODE_API_KEY", "Invalid source node API key.")

    ttl = int(target_node.get("peer_token_ttl") or 120)
    token = issue_peer_token(
        secret=str(target_node.get("peer_verify_secret") or ""),
        source_node_id=source_node_id,
        source_core_id=source_core_id,
        target_node_id=target_node_id,
        target_core_id=target_core_id,
        ttl_seconds=ttl,
    )
    return {
        "ok": True,
        "token": token,
        "expires_in": ttl,
        "refresh_after": int(target_node.get("peer_token_refresh_interval") or 30),
    }


@router.post("/api/nodes/{node_id}/sync-runtime")
async def api_sync_one_node_runtime(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    node = get_node(node_id)
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    result = await sync_node_runtime_once(node)
    return {"ok": bool(result.get("ok")), "node_id": node_id, "runtime": get_node_runtime(node_id), "sync": result}


@router.get("/api/nodes/{node_id}/runtime")
async def api_get_one_node_runtime(node_id: str, refresh: bool = Query(False), user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    node = get_node(node_id)
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    sync = None
    if refresh:
        sync = await sync_node_runtime_once(node)
    return {"ok": True, "node_id": node_id, "runtime": get_node_runtime(node_id), "sync": sync}


@router.get("/api/nodes/{node_id}/drift")
async def api_get_node_drift(node_id: str, refresh: bool = Query(False), user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    node = get_node(node_id)
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    if refresh:
        await sync_node_runtime_once(node)
    desired = build_node_config(node_id)
    runtime_entry = get_node_runtime(node_id)
    return {"ok": True, "drift": detect_node_drift(node_id, desired, runtime_entry)}


@router.post("/api/nodes/sync-runtime")
async def api_sync_all_node_runtime(user: str = Depends(require_admin)) -> dict:
    nodes = list_nodes()
    results = await sync_all_node_runtime(nodes)
    return {"ok": True, "message": "Node runtime cache sync finished.", "nodes": len(nodes), "results": results}


@router.get("/api/nodes/runtime-cache")
async def api_node_runtime_cache(user: str = Depends(require_admin)) -> dict:
    from ..node_runtime_cache import load_cache

    return {"ok": True, "cache": load_cache()}


@router.post("/api/nodes/check")
async def api_check_unsaved_node(body: NodeBody, user: str = Depends(require_admin)) -> dict:
    return await check_node_payload(pydantic_to_dict(body))


@router.post("/api/nodes/{node_id}/check")
async def api_check_saved_node(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    node = get_node(node_id)
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    result = await check_node_payload(node)
    updated = set_node_check_result(
        node_id,
        ok=bool(result.get("ok")),
        error=str(result.get("message", "")),
        details=result,
    )
    return {**result, "node": updated}


@router.get("/api/nodes/{node_id}/inbounds")
async def api_node_inbounds(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    if not get_node(node_id):
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    return {"ok": True, "inbounds": inbound_catalog(node_id)}


@router.get("/api/nodes/{node_id}/config-preview")
async def api_node_config_preview(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    if not get_node(node_id):
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    return {"ok": True, "config": build_node_config(node_id)}


@router.post("/api/nodes/{node_id}/apply-config")
async def api_apply_node_config(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    node = get_node(node_id)
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    payload = build_node_config(node_id)
    try:
        data = await asyncio.to_thread(post_node_api, node, "/config/apply", payload)
        changed = set_node_cores_apply_result(node_id, ok=True)
        await sync_node_runtime_once(node)
        runtime_entry = get_node_runtime(node_id)
        logger.info("node config applied: node_id=%s cores=%s by=%s", node_id, len(payload.get("cores", [])), user)
        return {
            "ok": True,
            "message": f"Applied {len(payload.get('cores', []))} core configuration(s) to {node.get('name') or node.get('address')}.",
            "node_response": data,
            "runtime": runtime_entry,
            "updated_cores": changed,
        }
    except NodeAPIError as exc:
        set_node_cores_apply_result(node_id, ok=False, error=str(exc))
        logger.warning("node config apply failed: node_id=%s error=%s", node_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
