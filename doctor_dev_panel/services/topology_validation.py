
from __future__ import annotations

from ..api_errors import api_error
from ..id_utils import is_valid_core_id, is_valid_node_id


def require_node_id(node_id: str) -> str:
    if not is_valid_node_id(node_id):
        raise api_error(400, "INVALID_NODE_ID", "Invalid node identifier. Refresh the page and try again.")
    return node_id


def require_core_id(core_id: str) -> str:
    if not is_valid_core_id(core_id):
        raise api_error(400, "INVALID_CORE_ID", "Invalid core identifier. Refresh the page and try again.")
    return core_id





