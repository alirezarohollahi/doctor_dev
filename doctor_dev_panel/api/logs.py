from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query

from ..api_errors import api_error
from ..auth import require_admin
from ..deps import require_node_id
from ..logging_utils import filter_lines, panel_log_file, tail_file
from ..node_store import get_node, list_nodes
from ..services.node_control import NodeAPIError, read_node_api

logger = logging.getLogger("doctor_dev_panel.api.logs")
router = APIRouter()


@router.get("/api/logs/sources")
async def api_log_sources(user: str = Depends(require_admin)) -> dict:
    sources = [{"id": "panel", "label": "Panel logs", "kind": "panel", "status": "local"}]
    for node in list_nodes():
        sources.append(
            {
                "id": f"node:{node.get('id')}",
                "label": f"Node: {node.get('name') or node.get('address')}",
                "kind": "node",
                "node_id": node.get("id"),
                "status": node.get("status", "pending"),
            }
        )
    return {"ok": True, "sources": sources}


@router.get("/api/logs")
async def api_logs(
    source: str = Query("panel"),
    limit: int = Query(300, ge=1, le=5000),
    level: str = Query("all"),
    q: str = Query(""),
    user: str = Depends(require_admin),
) -> dict:
    logger.info("logs requested source=%s limit=%s level=%s query=%s by=%s", source, limit, level, q, user)
    if source == "panel":
        path = panel_log_file()
        lines = filter_lines(tail_file(path, limit=max(limit, 1)), level=level, query=q)
        return {"ok": True, "source": "panel", "path": str(path), "lines": lines[-limit:], "level": level, "query": q}

    if source.startswith("node:"):
        node_id = require_node_id(source.split(":", 1)[1])
        node = get_node(node_id)
        if not node:
            raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
        try:
            qs = "?" + urlencode({"limit": limit, "level": level, "q": q})
            data = await asyncio.to_thread(read_node_api, node, f"/logs{qs}")
            return {
                "ok": True,
                "source": source,
                "node": node,
                "lines": data.get("lines", []),
                "path": data.get("path", ""),
                "level": level,
                "query": q,
            }
        except NodeAPIError as exc:
            logger.warning("cannot read node logs: node_id=%s error=%s", node_id, exc)
            return {"ok": False, "source": source, "node": node, "lines": [], "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.warning("cannot read node logs: node_id=%s unexpected=%s", node_id, exc)
            return {"ok": False, "source": source, "node": node, "lines": [], "error": "Unexpected node log error. Check panel logs for details."}

    raise HTTPException(status_code=400, detail="Unknown log source.")
