from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi import Request as FastAPIRequest
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .admin_store import list_admins
from .auth import authenticate, make_session, require_admin
from .config import APP_TITLE, SECURITY_HEADERS, SESSION_COOKIE, WEB_DIR
from .core_store import (
    build_node_config,
    create_core,
    get_core,
    inbound_catalog,
    list_cores,
    remove_core,
    update_core,
)
from .logging_utils import filter_lines, panel_log_file, setup_panel_logging, tail_file
from .node_store import (
    create_node,
    generate_api_key,
    get_node,
    list_nodes,
    remove_node,
    set_node_check_result,
    update_node,
)
from .schemas import CoreBody, LoginBody, NodeBody

setup_panel_logging()
logger = logging.getLogger("doctor_dev_panel.app")
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


def _read_url(
    url: str, api_key: str = "", *, certificate: str = "", timeout: float = 4.0
) -> tuple[int, dict]:
    headers = {"Accept": "application/json", "User-Agent": "DoctorDevPanel/NodeCheck"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(url, headers=headers)
    context = None
    if url.startswith("https://"):
        if certificate.strip():
            context = ssl.create_default_context(cadata=certificate)
        else:
            context = ssl._create_unverified_context()  # noqa: SLF001
    with urlopen(req, timeout=timeout, context=context) as response:  # noqa: S310 - admin configured node URL
        raw = response.read(1024 * 64).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw[:2000]}
        return int(response.status), data


def _check_node_sync(payload: dict) -> dict:
    host, explicit_scheme = _node_host(str(payload.get("address", "")))
    # API_PORT is the control-plane/management port. Node Port is the data-plane
    # listener port and is not used for panel health/status checks.
    port = int(payload.get("api_port") or 62051)
    api_key = str(payload.get("api_key") or "")
    certificate = str(payload.get("certificate") or "").strip()

    if explicit_scheme:
        schemes = [explicit_scheme]
    elif certificate:
        schemes = ["https"]
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
                status_code, data = _read_url(
                    url, key, certificate=certificate if scheme == "https" else ""
                )
                if 200 <= status_code < 300:
                    return {
                        "ok": True,
                        "status": "running",
                        "url": url,
                        "http_status": status_code,
                        "using_api_port": port,
                        "using_tls_certificate": bool(
                            certificate and scheme == "https"
                        ),
                        "response": data,
                        "message": "Node API is reachable.",
                    }
                last_error = f"{url} returned HTTP {status_code}"
            except HTTPError as exc:
                last_error = f"{url} returned HTTP {exc.code}"
            except (URLError, TimeoutError, OSError, ssl.SSLError, ValueError) as exc:
                last_error = f"{url} failed: {exc}"
            attempts.append(last_error)
    return {
        "ok": False,
        "status": "error",
        "message": last_error or "Node API check failed.",
        "attempts": attempts[-6:],
        "using_api_port": port,
    }


async def check_node_payload(payload: dict) -> dict:
    return await asyncio.to_thread(_check_node_sync, payload)


def _node_api_url(node: dict, path: str) -> tuple[str, str, str]:
    host, explicit_scheme = _node_host(str(node.get("address", "")))
    certificate = str(node.get("certificate") or "").strip()
    scheme = explicit_scheme or ("https" if certificate else "http")
    port = int(node.get("api_port") or 62051)
    return f"{scheme}://{host}:{port}{path}", scheme, certificate


def _read_node_api(node: dict, path: str, *, timeout: float = 5.0) -> dict:
    url, scheme, certificate = _node_api_url(node, path)
    status_code, data = _read_url(
        url,
        str(node.get("api_key") or ""),
        certificate=certificate if scheme == "https" else "",
        timeout=timeout,
    )
    if not (200 <= status_code < 300):
        raise RuntimeError(f"{url} returned HTTP {status_code}")
    return data


@app.middleware("http")
async def security_headers(request: FastAPIRequest, call_next):
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled request error: %s %s", request.method, request.url.path
        )
        raise
    for key, value in SECURITY_HEADERS.items():
        response.headers[key] = value
    response.headers["X-Doctor-Dev"] = APP_TITLE
    if request.url.path.startswith("/api/") or request.url.path == "/health":
        logger.info(
            "%s %s -> %s", request.method, request.url.path, response.status_code
        )
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
    secure_cookie = (
        os.getenv("COOKIE_SECURE", "0") == "1" or os.getenv("USE_TLS", "0") == "1"
    )
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
        "phase": "core-editor-ui-foundation",
        "nodes_total": len(nodes),
        "nodes_enabled": len([node for node in nodes if node.get("enabled")]),
        "message": "Node API checks, TLS certificate handling and the core editor UI are ready.",
        "cores_total": len(list_cores()),
    }


@app.get("/api/panel/stats")
async def panel_stats(user: str = Depends(require_admin)) -> dict:
    nodes = list_nodes()
    cores = list_cores()

    running_nodes = [
        n for n in nodes if n.get("status") == "running" and n.get("enabled")
    ]
    error_nodes = [n for n in nodes if n.get("status") == "error" and n.get("enabled")]
    pending_nodes = [
        n for n in nodes if n.get("status") == "pending" and n.get("enabled")
    ]
    disabled_nodes = [n for n in nodes if not n.get("enabled")]

    enabled_cores = [c for c in cores if c.get("enabled")]
    total_inbounds = sum(len(c.get("inbounds", [])) for c in cores)
    enabled_inbounds = sum(
        sum(1 for ib in c.get("inbounds", []) if ib.get("enabled", True))
        for c in enabled_cores
    )
    total_balancers = sum(len(c.get("balancers", [])) for c in cores)

    return {
        "ok": True,
        "nodes": {
            "total": len(nodes),
            "running": len(running_nodes),
            "error": len(error_nodes),
            "pending": len(pending_nodes),
            "disabled": len(disabled_nodes),
        },
        "cores": {
            "total": len(cores),
            "enabled": len(enabled_cores),
            "disabled": len(cores) - len(enabled_cores),
        },
        "inbounds": {
            "total": total_inbounds,
            "enabled": enabled_inbounds,
        },
        "balancers": {
            "total": total_balancers,
        },
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
async def api_update_node(
    node_id: str, body: NodeBody, user: str = Depends(require_admin)
) -> dict:
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
async def api_check_unsaved_node(
    body: NodeBody, user: str = Depends(require_admin)
) -> dict:
    result = await check_node_payload(body.model_dump())
    return result


@app.post("/api/nodes/{node_id}/check")
async def api_check_saved_node(
    node_id: str, user: str = Depends(require_admin)
) -> dict:
    node = get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found.")
    result = await check_node_payload(node)
    updated = set_node_check_result(
        node_id,
        ok=bool(result.get("ok")),
        error=str(result.get("message", "")),
        details=result,
    )
    return {**result, "node": updated}


@app.get("/api/cores")
async def api_list_cores(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "cores": list_cores(), "inbound_catalog": inbound_catalog()}


@app.post("/api/cores")
async def api_create_core(body: CoreBody, user: str = Depends(require_admin)) -> dict:
    if not get_node(body.node_id):
        raise HTTPException(status_code=400, detail="Selected node does not exist.")
    core = create_core(body.model_dump())
    logger.info(
        "core created: id=%s name=%s node_id=%s by=%s",
        core.get("id"),
        core.get("name"),
        core.get("node_id"),
        user,
    )
    return {"ok": True, "core": core}


@app.put("/api/cores/{core_id}")
async def api_update_core(
    core_id: str, body: CoreBody, user: str = Depends(require_admin)
) -> dict:
    if not get_node(body.node_id):
        raise HTTPException(status_code=400, detail="Selected node does not exist.")
    core = update_core(core_id, body.model_dump())
    if not core:
        raise HTTPException(status_code=404, detail="Core not found.")
    logger.info(
        "core updated: id=%s name=%s node_id=%s by=%s",
        core.get("id"),
        core.get("name"),
        core.get("node_id"),
        user,
    )
    return {"ok": True, "core": core}


@app.delete("/api/cores/{core_id}")
async def api_delete_core(core_id: str, user: str = Depends(require_admin)) -> dict:
    if not remove_core(core_id):
        raise HTTPException(status_code=404, detail="Core not found.")
    logger.info("core deleted: id=%s by=%s", core_id, user)
    return {"ok": True}


@app.get("/api/cores/{core_id}/preview")
async def api_core_preview(core_id: str, user: str = Depends(require_admin)) -> dict:
    core = get_core(core_id)
    if not core:
        raise HTTPException(status_code=404, detail="Core not found.")
    return {
        "ok": True,
        "core": core,
        "node_config_preview": build_node_config(str(core.get("node_id"))),
    }


@app.get("/api/nodes/{node_id}/inbounds")
async def api_node_inbounds(node_id: str, user: str = Depends(require_admin)) -> dict:
    if not get_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found.")
    return {"ok": True, "inbounds": inbound_catalog(node_id)}


@app.get("/api/nodes/{node_id}/config-preview")
async def api_node_config_preview(
    node_id: str, user: str = Depends(require_admin)
) -> dict:
    if not get_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found.")
    return {"ok": True, "config": build_node_config(node_id)}


@app.get("/api/logs/sources")
async def api_log_sources(user: str = Depends(require_admin)) -> dict:
    nodes = list_nodes()
    sources = [
        {"id": "panel", "label": "Panel logs", "kind": "panel", "status": "local"}
    ]
    for node in nodes:
        sources.append(
            {
                "id": f"node:{node.get('id')}",
                "label": f"Node: {node.get('name') or node.get('address')}",
                "kind": "node",
                "node_id": node.get("id"),
                "status": node.get("status", "pending"),
            }
        )
    return {"ok": True, "sources": sources}


@app.get("/api/logs")
async def api_logs(
    source: str = Query("panel"),
    limit: int = Query(300, ge=1, le=5000),
    level: str = Query("all"),
    q: str = Query(""),
    user: str = Depends(require_admin),
) -> dict:
    logger.info(
        "logs requested source=%s limit=%s level=%s query=%s by=%s",
        source,
        limit,
        level,
        q,
        user,
    )
    if source == "panel":
        path = panel_log_file()
        lines = filter_lines(tail_file(path, limit=max(limit, 1)), level=level, query=q)
        return {
            "ok": True,
            "source": "panel",
            "path": str(path),
            "lines": lines[-limit:],
            "level": level,
            "query": q,
        }
    if source.startswith("node:"):
        node_id = source.split(":", 1)[1]
        node = get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found.")
        try:
            qs = "?" + urlencode({"limit": limit, "level": level, "q": q})
            data = await asyncio.to_thread(_read_node_api, node, f"/logs{qs}")
            return {
                "ok": True,
                "source": source,
                "node": node,
                "lines": data.get("lines", []),
                "path": data.get("path", ""),
                "level": level,
                "query": q,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("cannot read node logs: node_id=%s", node_id)
            return {
                "ok": False,
                "source": source,
                "node": node,
                "lines": [],
                "error": str(exc),
            }
    raise HTTPException(status_code=400, detail="Unknown log source.")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": APP_TITLE, "version": __version__}
