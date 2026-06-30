
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..auth import authenticate, make_session, require_admin
from ..config import SESSION_COOKIE
from ..schemas import LoginBody

router = APIRouter()


@router.post("/api/auth/login")
async def login(body: LoginBody) -> JSONResponse:
    if not authenticate(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    response = JSONResponse({"ok": True, "username": body.username})
    secure_cookie = os.getenv("COOKIE_SECURE", "0") == "1"
    response.set_cookie(
        SESSION_COOKIE,
        make_session(body.username),
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        max_age=int(os.getenv("SESSION_TTL_SECONDS", "43200")),
    )
    return response


@router.post("/api/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/api/auth/me")
async def me(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "username": user}



