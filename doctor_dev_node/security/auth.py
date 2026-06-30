
from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException


def api_key() -> str:
    return os.getenv("API_KEY", "")


def check_auth(authorization: Optional[str]) -> None:
    key = api_key()
    if not key:
        return
    if authorization != f"Bearer {key}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")





