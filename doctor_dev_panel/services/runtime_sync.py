
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Iterable

from ..node_runtime_cache import mark_node_runtime_error, update_node_runtime
from .node_control import NodeAPIError, read_node_export

logger = logging.getLogger("doctor_dev_panel.services.runtime_sync")


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 10_000) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def runtime_sync_concurrency() -> int:
    """Maximum number of nodes the panel syncs at the same time.

    This prevents a large node list from spawning an unbounded number of
    worker-thread HTTP requests during runtime refreshes. The default is high
    enough for small deployments and safe for constrained servers.
    """

    return _env_int("DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY", 16, minimum=1, maximum=256)


def _dedupe_nodes(nodes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        result.append(node)
    return result


async def sync_node_runtime_once(node: dict[str, Any]) -> dict[str, Any]:
    """Fetch one node's live runtime and update the panel runtime cache."""

    node_id = str(node.get("id") or "")
    try:
        payload = await asyncio.to_thread(read_node_export, node)
        update_node_runtime(node_id, payload)
        return {"ok": True, "node_id": node_id, "payload": payload}
    except NodeAPIError as exc:
        mark_node_runtime_error(node_id, str(exc))
        logger.warning("runtime sync failed: node_id=%s error=%s", node_id, exc)
        return {"ok": False, "node_id": node_id, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        mark_node_runtime_error(node_id, "Unexpected runtime sync error.")
        logger.exception("runtime sync crashed: node_id=%s", node_id)
        return {"ok": False, "node_id": node_id, "error": "Unexpected runtime sync error."}


async def sync_all_node_runtime(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sync all nodes with bounded concurrency and stable result ordering."""

    cleaned_nodes = _dedupe_nodes(nodes)
    if not cleaned_nodes:
        return []

    semaphore = asyncio.Semaphore(runtime_sync_concurrency())

    async def guarded(node: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await sync_node_runtime_once(node)

    results = await asyncio.gather(*(guarded(node) for node in cleaned_nodes), return_exceptions=True)
    cleaned: list[dict[str, Any]] = []
    for node, result in zip(cleaned_nodes, results):
        if isinstance(result, Exception):
            node_id = str(node.get("id") or "")
            cleaned.append({"ok": False, "node_id": node_id, "error": str(result)})
        elif isinstance(result, dict):
            cleaned.append(result)
    return cleaned



