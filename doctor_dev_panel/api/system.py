from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from .. import __version__
from ..admin_store import list_admins
from ..auth import require_admin
from ..config import APP_TITLE
from ..core_store import list_cores
from ..integrity import inspect_integrity, repair_integrity
from ..node_store import list_nodes

logger = logging.getLogger("doctor_dev_panel.api.system")
router = APIRouter()


@router.get("/api/panel/summary")
async def panel_summary(user: str = Depends(require_admin)) -> dict:
    nodes = list_nodes()
    return {
        "ok": True,
        "user": user,
        "nodes_total": len(nodes),
        "nodes_enabled": len([node for node in nodes if node.get("enabled")]),
        "message": "Panel is ready.",
        "cores_total": len(list_cores()),
    }


@router.get("/api/panel/stats")
async def panel_stats(user: str = Depends(require_admin)) -> dict:
    nodes = list_nodes()
    cores = list_cores()
    running_nodes = [n for n in nodes if n.get("status") == "running" and n.get("enabled")]
    error_nodes = [n for n in nodes if n.get("status") == "error" and n.get("enabled")]
    pending_nodes = [n for n in nodes if n.get("status") == "pending" and n.get("enabled")]
    disabled_nodes = [n for n in nodes if not n.get("enabled")]
    enabled_cores = [c for c in cores if c.get("enabled")]
    total_inbounds = sum(len(c.get("inbounds", [])) for c in cores)
    enabled_inbounds = sum(
        sum(1 for ib in c.get("inbounds", []) if ib.get("enabled", True))
        for c in enabled_cores
    )
    total_balancers = sum(len(c.get("balancers", [])) for c in cores)
    return {
        "ok": True,
        "nodes": {
            "total": len(nodes),
            "running": len(running_nodes),
            "error": len(error_nodes),
            "pending": len(pending_nodes),
            "disabled": len(disabled_nodes),
        },
        "cores": {
            "total": len(cores),
            "enabled": len(enabled_cores),
            "disabled": len(cores) - len(enabled_cores),
        },
        "inbounds": {"total": total_inbounds, "enabled": enabled_inbounds},
        "balancers": {"total": total_balancers},
    }


@router.get("/api/panel/integrity")
async def panel_integrity(user: str = Depends(require_admin)) -> dict:
    return inspect_integrity()


@router.post("/api/panel/repair")
async def panel_repair(user: str = Depends(require_admin)) -> dict:
    result = repair_integrity()
    logger.warning("data integrity repair executed by=%s changes=%s", user, result.get("changes"))
    return result


@router.get("/api/admins")
async def admins(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "admins": list_admins()}


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": APP_TITLE, "version": __version__}
