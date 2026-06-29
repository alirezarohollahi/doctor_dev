from __future__ import annotations

from typing import Any

from .core_store import load_store as load_core_store
from .core_store import normalize_core, save_store as save_core_store
from .id_utils import clean_identifier, is_valid_core_id, is_valid_node_id
from .node_store import load_store as load_node_store
from .node_store import normalize_node, save_store as save_node_store


def _short(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "id": clean_identifier(item.get("id")),
        "name": clean_identifier(item.get("name")),
    }


def inspect_integrity() -> dict[str, Any]:
    node_store = load_node_store()
    core_store = load_core_store()
    raw_nodes = node_store.get("nodes", []) if isinstance(node_store.get("nodes"), list) else []
    raw_cores = core_store.get("cores", []) if isinstance(core_store.get("cores"), list) else []

    invalid_nodes: list[dict[str, Any]] = []
    valid_node_ids: set[str] = set()
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict) or not is_valid_node_id(node.get("id")):
            invalid_nodes.append(_short(node if isinstance(node, dict) else {}, index))
            continue
        valid_node_ids.add(str(node.get("id")))

    invalid_cores: list[dict[str, Any]] = []
    orphan_cores: list[dict[str, Any]] = []
    disabled_orphan_cores: list[dict[str, Any]] = []
    for index, core in enumerate(raw_cores):
        if not isinstance(core, dict) or not is_valid_core_id(core.get("id")):
            invalid_cores.append(_short(core if isinstance(core, dict) else {}, index))
            continue
        node_id = clean_identifier(core.get("node_id"))
        if not is_valid_node_id(node_id) or node_id not in valid_node_ids:
            entry = _short(core, index)
            entry["node_id"] = node_id
            if core.get("enabled") is False:
                disabled_orphan_cores.append(entry)
            else:
                orphan_cores.append(entry)

    problems_total = len(invalid_nodes) + len(invalid_cores) + len(orphan_cores)
    return {
        "ok": True,
        "healthy": problems_total == 0,
        "summary": {
            "nodes_total_raw": len(raw_nodes),
            "nodes_valid": len(valid_node_ids),
            "cores_total_raw": len(raw_cores),
            "invalid_nodes": len(invalid_nodes),
            "invalid_cores": len(invalid_cores),
            "orphan_cores": len(orphan_cores),
            "disabled_orphan_cores": len(disabled_orphan_cores),
            "problems_total": problems_total,
        },
        "invalid_nodes": invalid_nodes,
        "invalid_cores": invalid_cores,
        "orphan_cores": orphan_cores,
        "disabled_orphan_cores": disabled_orphan_cores,
    }


def repair_integrity() -> dict[str, Any]:
    node_store = load_node_store()
    core_store = load_core_store()
    raw_nodes = node_store.get("nodes", []) if isinstance(node_store.get("nodes"), list) else []
    raw_cores = core_store.get("cores", []) if isinstance(core_store.get("cores"), list) else []

    kept_nodes: list[dict[str, Any]] = []
    removed_nodes: list[dict[str, Any]] = []
    valid_node_ids: set[str] = set()
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict) or not is_valid_node_id(node.get("id")):
            removed_nodes.append(_short(node if isinstance(node, dict) else {}, index))
            continue
        normalized = normalize_node(node, existing=node)
        kept_nodes.append(normalized)
        valid_node_ids.add(str(normalized.get("id")))

    kept_cores: list[dict[str, Any]] = []
    removed_cores: list[dict[str, Any]] = []
    disabled_orphans: list[dict[str, Any]] = []
    for index, core in enumerate(raw_cores):
        if not isinstance(core, dict) or not is_valid_core_id(core.get("id")):
            removed_cores.append(_short(core if isinstance(core, dict) else {}, index))
            continue
        normalized = normalize_core(core, existing=core)
        node_id = clean_identifier(normalized.get("node_id"))
        if not is_valid_node_id(node_id) or node_id not in valid_node_ids:
            normalized["enabled"] = False
            normalized["status"] = "disabled"
            normalized["last_error"] = "This core was disabled because its linked node is missing or invalid. Select a valid node and save it again."
            entry = _short(normalized, index)
            entry["node_id"] = node_id
            disabled_orphans.append(entry)
        kept_cores.append(normalized)

    node_store["version"] = 3
    node_store["nodes"] = kept_nodes
    save_node_store(node_store)

    core_store["version"] = 1
    core_store["cores"] = kept_cores
    save_core_store(core_store)

    after = inspect_integrity()
    return {
        "ok": True,
        "message": "Data repair completed.",
        "changes": {
            "removed_invalid_nodes": removed_nodes,
            "removed_invalid_cores": removed_cores,
            "disabled_orphan_cores": disabled_orphans,
        },
        "integrity": after,
    }




