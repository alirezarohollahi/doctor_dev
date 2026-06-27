from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .admin_store import list_admins
from .auth import authenticate, make_session, require_admin
from .config import APP_TITLE, SECURITY_HEADERS, SESSION_COOKIE, WEB_DIR
from .node_store import create_node, generate_api_key, list_nodes, remove_node, update_node
from .schemas import LoginBody, NodeBody

app = FastAPI(title=APP_TITLE, version=__version__, docs_url=None, redoc_url=None)

assets_dir = WEB_DIR / "assets"
app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers[key] = value
    response.headers["X-Doctor-Dev"] = APP_TITLE
    return response


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/admin")
async def admin() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


@app.post("/api/auth/login")
async def login(body: LoginBody) -> JSONResponse:
    if not authenticate(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    response = JSONResponse({"ok": True, "username": body.username})
    secure_cookie = os.getenv("COOKIE_SECURE", "0") == "1" or os.getenv("USE_TLS", "0") == "1"
    response.set_cookie(
        SESSION_COOKIE,
        make_session(body.username),
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        max_age=int(os.getenv("SESSION_TTL_SECONDS", "43200")),
    )
    return response


@app.post("/api/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/auth/me")
async def me(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "username": user}


@app.get("/api/panel/summary")
async def panel_summary(user: str = Depends(require_admin)) -> dict:
    nodes = list_nodes()
    return {
        "ok": True,
        "user": user,
        "phase": "node-foundation",
        "nodes_total": len(nodes),
        "nodes_enabled": len([node for node in nodes if node.get("enabled")]),
        "message": "Node foundation is ready. Runtime actions will be added in the next phases.",
    }


@app.get("/api/admins")
async def admins(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "admins": list_admins()}


@app.get("/api/nodes")
async def api_list_nodes(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "nodes": list_nodes()}


@app.post("/api/nodes")
async def api_create_node(body: NodeBody, user: str = Depends(require_admin)) -> dict:
    node = create_node(body.model_dump())
    return {"ok": True, "node": node}


@app.put("/api/nodes/{node_id}")
async def api_update_node(node_id: str, body: NodeBody, user: str = Depends(require_admin)) -> dict:
    node = update_node(node_id, body.model_dump())
    if not node:
        raise HTTPException(status_code=404, detail="Node not found.")
    return {"ok": True, "node": node}


@app.delete("/api/nodes/{node_id}")
async def api_delete_node(node_id: str, user: str = Depends(require_admin)) -> dict:
    if not remove_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found.")
    return {"ok": True}


@app.post("/api/nodes/api-key")
async def api_generate_node_key(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "api_key": generate_api_key()}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": APP_TITLE, "version": __version__}
