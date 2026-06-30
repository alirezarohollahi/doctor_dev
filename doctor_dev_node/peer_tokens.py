
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_peer_token(*, secret: str, source_node_id: str, source_core_id: str, target_node_id: str, target_core_id: str, ttl_seconds: int) -> str:
    if not secret:
        raise ValueError("peer token secret is missing")
    now = int(time.time())
    ttl = min(max(int(ttl_seconds or 120), 10), 86400)
    payload = {
        "typ": "doctor-dev-peer",
        "iat": now,
        "exp": now + ttl,
        "source_node_id": source_node_id,
        "source_core_id": source_core_id,
        "target_node_id": target_node_id,
        "target_core_id": target_core_id,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


def verify_peer_token(token: str, *, secret: str, target_node_id: str = "", target_core_id: str = "") -> dict[str, Any]:
    if not token or "." not in token or not secret:
        raise ValueError("invalid peer token")
    body, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise ValueError("bad peer token signature")
    payload = json.loads(_unb64(body).decode("utf-8"))
    if payload.get("typ") != "doctor-dev-peer":
        raise ValueError("bad peer token type")
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("peer token expired")
    if target_node_id and payload.get("target_node_id") != target_node_id:
        raise ValueError("peer token target node mismatch")
    if target_core_id and payload.get("target_core_id") != target_core_id:
        raise ValueError("peer token target core mismatch")
    return payload





