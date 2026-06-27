from __future__ import annotations

import asyncio
import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .admin_store import list_admins
from .auth import authenticate, make_session, require_admin
from .config import APP_TITLE, SECURITY_HEADERS, SESSION_COOKIE, WEB_DIR
from .node_store import create_node, generate_api_key, get_node, list_nodes, remove_node, set_node_check_result, update_node
from .schemas import LoginBody, NodeBody

app = FastAPI(title=APP_TITLE, version=__version__, docs_url=None, redoc_url=None)

assets_dir = WEB_DIR / "assets"
app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


def _node_host(address: str) -> tuple[str, str | None]:
    raw = (address or "").strip()
    if not raw:
        raise ValueError("Node address is empty.")
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    scheme = parsed.scheme if "://" in raw else None
    host = parsed.netloc or parsed.path
    host = host.split("/", 1)[0].strip()
    if not host:
        raise ValueError("Node address is invalid.")
    return host, scheme


def _read_url(url: str, api_key: str = "", *, timeout: float = 4.0) -> tuple[int, dict]:
    headers = {"Accept": "application/json", "User-Agent": "DoctorDevPanel/NodeCheck"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(url, headers=headers)
    context = ssl._create_unverified_context() if url.startswith("https://") else None  # noqa: SLF001
    with urlopen(req, timeout=timeout, context=context) as response:  # noqa: S310 - admin configured node URL
        raw = response.read(1024 * 64).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw[:2000]}
        return int(response.status), data


def _check_node_sync(payload: dict) -> dict:
    host, explicit_scheme = _node_host(str(payload.get("address", "")))
    port = int(payload.get("node_port") or 62050)
    api_key = str(payload.get("api_key") or "")
    certificate = str(payload.get("certificate") or "").strip()

    if explicit_scheme:
        schemes = [explicit_scheme]
    elif certificate:
        schemes = ["https", "http"]
    else:
        schemes = ["http", "https"]

    attempts: list[str] = []
    last_error = ""
    for scheme in schemes:
        base = f"{scheme}://{host}:{port}"
        endpoints = [("/status", api_key), ("/health", "")]
        for endpoint, key in endpoints:
            if endpoint == "/status" and not key:
                continue
            url = base + endpoint
            try:
                status_code, data = _read_url(url, key)
                if 200 <= status_code < 300:
                    return {
                        "ok": True,
                        "status": "running",
                        "url": url,
                        "http_status": status_code,
                        "response": data,
                        "message": "Node is reachable.",
                    }
                last_error = f"{url} returned HTTP {status_code}"
            except HTTPError as exc:
                last_error = f"{url} returned HTTP {exc.code}"
            except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
                last_error = f"{url} failed: {exc}"
            attempts.append(last_error)
    return {"ok": False, "status": "error", "message": last_error or "Node check failed.", "attempts": attempts[-6:]}


async def check_node_payload(payload: dict) -> dict:
    return await asyncio.to_thread(_check_node_sync, payload)


@app.middleware("http")
async def security_headers(request: FastAPIRequest, call_next):
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
        "phase": "node-status-service-foundation",
        "nodes_total": len(nodes),
        "nodes_enabled": len([node for node in nodes if node.get("enabled")]),
        "message": "Node inventory, status check and service management foundation are ready.",
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


@app.post("/api/nodes/check")
async def api_check_unsaved_node(body: NodeBody, user: str = Depends(require_admin)) -> dict:
    result = await check_node_payload(body.model_dump())
    return result


@app.post("/api/nodes/{node_id}/check")
async def api_check_saved_node(node_id: str, user: str = Depends(require_admin)) -> dict:
    node = get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found.")
    result = await check_node_payload(node)
    updated = set_node_check_result(node_id, ok=bool(result.get("ok")), error=str(result.get("message", "")), details=result)
    return {**result, "node": updated}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": APP_TITLE, "version": __version__}
