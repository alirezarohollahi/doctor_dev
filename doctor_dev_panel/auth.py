from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

from fastapi import HTTPException, Request

from .config import SESSION_COOKIE, SESSION_TTL_SECONDS
from .security import verify_password


def admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "admin")


def admin_password_hash() -> str:
    value = os.getenv("ADMIN_PASSWORD_HASH", "")
    if not value:
        # Development fallback only. The installer always writes ADMIN_PASSWORD_HASH.
        from .security import create_password_hash

        fallback = os.getenv("ADMIN_PASSWORD", "admin")
        value = create_password_hash(fallback)
        os.environ["ADMIN_PASSWORD_HASH"] = value
    return value


def app_secret() -> bytes:
    secret = os.getenv("APP_SECRET")
    if not secret or secret == "change-me-long-random-secret":
        secret = "dev-ephemeral-" + secrets.token_urlsafe(48)
        os.environ["APP_SECRET"] = secret
    return secret.encode("utf-8")


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_payload(payload: dict) -> str:
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(app_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_payload(token: str) -> Optional[dict]:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(app_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64_decode(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def authenticate(username: str, password: str) -> bool:
    return hmac.compare_digest(username, admin_username()) and verify_password(password, admin_password_hash())


def make_session(username: str) -> str:
    return sign_payload(
        {
            "sub": username,
            "iat": int(time.time()),
            "exp": int(time.time()) + SESSION_TTL_SECONDS,
            "nonce": secrets.token_hex(16),
        }
    )


async def require_admin(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    payload = verify_payload(token or "")
    if not payload:
        raise HTTPException(status_code=401, detail="login required")
    return str(payload.get("sub"))
