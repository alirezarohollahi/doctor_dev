from __future__ import annotations

import math
import re
from typing import Any

_INVALID_TEXT_VALUES = {"", "nan", "none", "null", "undefined", "[object object]"}
_NODE_ID_RE = re.compile(r"^node_[A-Za-z0-9_-]{6,96}$")
_CORE_ID_RE = re.compile(r"^core_[A-Za-z0-9_-]{6,96}$")


def clean_identifier(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def is_bad_identifier(value: Any) -> bool:
    text = clean_identifier(value)
    return text.lower() in _INVALID_TEXT_VALUES


def is_valid_node_id(value: Any) -> bool:
    text = clean_identifier(value)
    return not is_bad_identifier(text) and bool(_NODE_ID_RE.fullmatch(text))


def is_valid_core_id(value: Any) -> bool:
    text = clean_identifier(value)
    return not is_bad_identifier(text) and bool(_CORE_ID_RE.fullmatch(text))


def node_id_or_empty(value: Any) -> str:
    text = clean_identifier(value)
    return text if is_valid_node_id(text) else ""


def core_id_or_empty(value: Any) -> str:
    text = clean_identifier(value)
    return text if is_valid_core_id(text) else ""




