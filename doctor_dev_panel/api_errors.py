from __future__ import annotations

from fastapi import HTTPException


def api_error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"ok": False, "error_code": error_code, "message": message},
    )
