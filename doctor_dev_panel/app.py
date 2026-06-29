from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .api.auth import router as auth_router
from .api.cores import router as cores_router
from .api.logs import router as logs_router
from .api.nodes import router as nodes_router
from .api.system import router as system_router
from .config import APP_TITLE, SECURITY_HEADERS, WEB_DIR
from .logging_utils import (
    body_preview,
    debug_json,
    is_debug_enabled,
    redact_headers,
    setup_panel_logging,
)

setup_panel_logging()
logger = logging.getLogger("doctor_dev_panel.app")

app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None)

# Static assets must be mounted before the SPA fallback.
# Without this, /assets/*.css and /assets/*.js fall through to index.html,
# so browsers receive HTML for styles/scripts and show NS_ERROR_CORRUPTED_CONTENT.
ASSETS_DIR = WEB_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR), html=False), name="assets")


async def _capture_request_body(request: FastAPIRequest) -> bytes:
    body = await request.body()

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]
    return body


def _debug_request_meta(request: FastAPIRequest, body: bytes) -> dict:
    return {
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query or ""),
        "client": request.client.host if request.client else "",
        "headers": redact_headers(request.headers),
        "body": body_preview(body),
    }


@app.middleware("http")
async def security_headers(request: FastAPIRequest, call_next):
    started = time.perf_counter()
    debug = is_debug_enabled()
    if debug:
        try:
            request_body = await _capture_request_body(request)
            logger.debug("panel.request.start %s", debug_json(_debug_request_meta(request, request_body)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("panel.request.capture_failed method=%s path=%s error=%s", request.method, request.url.path, exc)
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception("unhandled request error: %s %s elapsed_ms=%s", request.method, request.url.path, elapsed_ms)
        raise

    for key, value in SECURITY_HEADERS.items():
        response.headers[key] = value
    response.headers["X-Doctor-Dev"] = APP_TITLE

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if request.url.path.startswith("/api/") or request.url.path == "/health":
        logger.info("%s %s -> %s %.2fms", request.method, request.url.path, response.status_code, elapsed_ms)
    if debug:
        logger.debug(
            "panel.request.end %s",
            debug_json(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "response_headers": redact_headers(response.headers),
                }
            ),
        )
    return response


app.include_router(auth_router)
app.include_router(system_router)
app.include_router(nodes_router)
app.include_router(cores_router)
app.include_router(logs_router)


@app.get("/favicon.ico", include_in_schema=False, response_model=None)
async def favicon():
    favicon_path = WEB_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/", response_model=None)
async def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/admin", response_model=None)
async def admin():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
async def spa_fallback(full_path: str):
    """Serve the single-page app for browser history routes only.

    Static/API paths must never fall through to index.html; otherwise browsers
    receive HTML with text/html for CSS/JS and report corrupted content.
    """
    path = (full_path or "").strip("/")
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found.")
    if path.startswith("assets/") or path in {"favicon.ico", "robots.txt", "manifest.json"}:
        raise HTTPException(status_code=404, detail="Static asset not found.")
    return FileResponse(str(WEB_DIR / "index.html"))
