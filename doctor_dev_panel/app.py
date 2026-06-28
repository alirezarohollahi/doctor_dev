from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import tempfile
import time
from http.client import RemoteDisconnected
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi import Request as FastAPIRequest
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .admin_store import list_admins
from .api_errors import api_error
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
    set_core_apply_result,
    set_node_cores_apply_result,
    disable_cores_for_node,
)
from .id_utils import is_valid_core_id, is_valid_node_id
from .integrity import inspect_integrity, repair_integrity
from .logging_utils import (
    body_preview,
    debug_json,
    filter_lines,
    is_debug_enabled,
    panel_log_file,
    redact_headers,
    setup_panel_logging,
    tail_file,
)
from .node_store import (
    create_node,
    generate_api_key,
    get_node,
    list_nodes,
    remove_node,
    set_node_check_result,
    update_node,
)
from .schemas import AdvancedConfigValidateBody, CoreBody, LoginBody, NodeBody

setup_panel_logging()
logger = logging.getLogger("doctor_dev_panel.app")


def require_node_id(node_id: str) -> str:
    if not is_valid_node_id(node_id):
        raise api_error(400, "INVALID_NODE_ID", "Invalid node identifier. Refresh the page and try again.")
    return node_id


def require_core_id(core_id: str) -> str:
    if not is_valid_core_id(core_id):
        raise api_error(400, "INVALID_CORE_ID", "Invalid core identifier. Refresh the page and try again.")
    return core_id


def _json_depth(value: object, depth: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return depth + 1
        return max(_json_depth(v, depth + 1) for v in value.values())
    if isinstance(value, list):
        if not value:
            return depth + 1
        return max(_json_depth(v, depth + 1) for v in value)
    return depth + 1


def _walk_json(value: object, path: str = "$") -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            items.extend(_walk_json(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(_walk_json(child, f"{path}[{index}]"))
    return items


def validate_manual_json_config(raw: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    text = (raw or "").strip()
    if not text:
        return {"valid": True, "errors": [], "warnings": ["Manual JSON is empty."], "normalized": None}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "errors": [f"Invalid JSON syntax at line {exc.lineno}, column {exc.colno}: {exc.msg}."],
            "warnings": [],
            "normalized": None,
        }
    if not isinstance(parsed, dict):
        errors.append("JSON root must be an object.")
        return {"valid": False, "errors": errors, "warnings": warnings, "normalized": None}

    depth = _json_depth(parsed)
    if depth > 64:
        errors.append("JSON is too deeply nested. Maximum supported depth is 64 levels.")

    # Xray-style shape checks when common sections are present.
    if "inbounds" in parsed and not isinstance(parsed.get("inbounds"), list):
        errors.append("Field 'inbounds' must be an array.")
    if "outbounds" in parsed and not isinstance(parsed.get("outbounds"), list):
        errors.append("Field 'outbounds' must be an array.")
    if "routing" in parsed and not isinstance(parsed.get("routing"), dict):
        errors.append("Field 'routing' must be an object.")

    seen_inbound_keys: set[tuple[str, int]] = set()
    inbounds = parsed.get("inbounds") if isinstance(parsed.get("inbounds"), list) else []
    for index, inbound in enumerate(inbounds):
        if not isinstance(inbound, dict):
            errors.append(f"inbounds[{index}] must be an object.")
            continue
        port = inbound.get("port")
        listen = str(inbound.get("listen") or "0.0.0.0")
        if port is None:
            warnings.append(f"inbounds[{index}] has no port field.")
        else:
            try:
                port_num = int(port)
                if not 1 <= port_num <= 65535:
                    errors.append(f"inbounds[{index}].port must be between 1 and 65535.")
                key = (listen, port_num)
                if key in seen_inbound_keys:
                    errors.append(f"Duplicate inbound listener {listen}:{port_num}.")
                seen_inbound_keys.add(key)
            except (TypeError, ValueError):
                errors.append(f"inbounds[{index}].port must be a number.")
        if not inbound.get("protocol"):
            warnings.append(f"inbounds[{index}] has no protocol field.")

    port_like_names = {"port", "target_port", "api_port", "node_port", "service_port", "listen_port"}
    for path, value in _walk_json(parsed):
        last = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if last in port_like_names and value not in (None, ""):
            try:
                port_num = int(value)
            except (TypeError, ValueError):
                errors.append(f"{path} must be a numeric port.")
                continue
            if not 1 <= port_num <= 65535:
                errors.append(f"{path} must be between 1 and 65535.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized": parsed if not errors else None,
    }


class NodeAPIError(RuntimeError):
    """Expected/clean node API failure shown to the UI without a traceback."""


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
    if is_debug_enabled():
        logger.debug("panel.node_api.request %s", debug_json({"method": "GET", "url": url, "headers": headers, "certificate_supplied": bool(certificate.strip())}))
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
        if is_debug_enabled():
            logger.debug("panel.node_api.response %s", debug_json({"url": url, "status": int(response.status), "body": data}))
        return int(response.status), data


def _node_scheme_candidates(address: str, certificate: str = "") -> tuple[str, list[str]]:
    host, explicit_scheme = _node_host(address)
    if explicit_scheme:
        return host, [explicit_scheme]
    # A stored certificate means "trust this certificate if the control API is HTTPS".
    # It must not force HTTPS because many nodes expose the control API over HTTP
    # while using certificates for data-plane or reverse-proxy paths. Try HTTPS
    # first when a certificate exists, then fall back to HTTP if the TLS handshake
    # is closed by the remote side.
    return host, (["https", "http"] if certificate.strip() else ["http", "https"])


def _format_attempts(attempts: list[str]) -> str:
    cleaned = [item for item in attempts if item]
    if not cleaned:
        return "No connection attempt was completed."
    return " | ".join(cleaned[-4:])


def _check_node_sync(payload: dict) -> dict:
    certificate = str(payload.get("certificate") or "").strip()
    host, schemes = _node_scheme_candidates(str(payload.get("address", "")), certificate)
    # api_port is the node control-plane/management API. node_port/service_port is
    # reserved for node data-plane traffic and must not be used for /health, /logs,
    # or /config/apply.
    port = int(payload.get("api_port") or 62051)
    api_key = str(payload.get("api_key") or "")

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
                    url, key, certificate=certificate if scheme == "https" else "", timeout=4.0
                )
                if 200 <= status_code < 300:
                    return {
                        "ok": True,
                        "status": "running",
                        "url": url,
                        "http_status": status_code,
                        "using_api_port": port,
                        "using_control_scheme": scheme,
                        "using_tls_certificate": bool(certificate and scheme == "https"),
                        "response": data,
                        "message": "Node connection is healthy.",
                    }
                last_error = f"{url} returned HTTP {status_code}"
            except HTTPError as exc:
                last_error = f"{url} returned HTTP {exc.code}"
            except (RemoteDisconnected, URLError, TimeoutError, OSError, ssl.SSLError, ValueError) as exc:
                last_error = f"{url} failed: {exc}"
            attempts.append(last_error)
    return {
        "ok": False,
        "status": "error",
        "message": last_error or "Node connection check failed.",
        "attempts": attempts[-6:],
        "using_api_port": port,
    }


async def check_node_payload(payload: dict) -> dict:
    return await asyncio.to_thread(_check_node_sync, payload)


def _node_api_urls(node: dict, path: str) -> list[tuple[str, str, str]]:
    certificate = str(node.get("certificate") or "").strip()
    host, schemes = _node_scheme_candidates(str(node.get("address", "")), certificate)
    port = int(node.get("api_port") or 62051)
    return [(f"{scheme}://{host}:{port}{path}", scheme, certificate) for scheme in schemes]


def _read_node_api(node: dict, path: str, *, timeout: float = 5.0) -> dict:
    attempts: list[str] = []
    api_key = str(node.get("api_key") or "")
    for url, scheme, certificate in _node_api_urls(node, path):
        try:
            status_code, data = _read_url(
                url,
                api_key,
                certificate=certificate if scheme == "https" else "",
                timeout=timeout,
            )
            if 200 <= status_code < 300:
                return data
            attempts.append(f"{url} returned HTTP {status_code}")
        except HTTPError as exc:
            if exc.code == 404 and path.startswith("/logs"):
                raise NodeAPIError(
                    "This node is running an older agent. Update the node service, restart it, then try again."
                ) from exc
            raise NodeAPIError(f"Node returned HTTP {exc.code} while handling {path}.") from exc
        except (RemoteDisconnected, URLError, TimeoutError, OSError, ssl.SSLError, ValueError) as exc:
            attempts.append(f"{url} failed: {exc}")
            continue
    raise NodeAPIError(
        "Node API is unreachable while handling "
        f"{path}. Check the API port, TLS/certificate, and node service. "
        f"Attempts: {_format_attempts(attempts)}"
    )


def _post_node_api(node: dict, path: str, payload: dict, *, timeout: float = 8.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    if is_debug_enabled():
        logger.debug("panel.node_api.apply_payload %s", debug_json({"path": path, "payload": payload}))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "DoctorDevPanel/NodeApply",
    }
    api_key = str(node.get("api_key") or "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    attempts: list[str] = []
    for url, scheme, certificate in _node_api_urls(node, path):
        context = None
        if scheme == "https":
            if certificate.strip():
                context = ssl.create_default_context(cadata=certificate)
            else:
                context = ssl._create_unverified_context()  # noqa: SLF001
        if is_debug_enabled():
            logger.debug("panel.node_api.request %s", debug_json({"method": "POST", "url": url, "headers": headers, "payload_bytes": len(body), "certificate_supplied": bool(certificate.strip())}))
        req = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout, context=context) as response:  # noqa: S310
                raw = response.read(1024 * 256).decode("utf-8", errors="replace")
                data = json.loads(raw) if raw else {}
                if is_debug_enabled():
                    logger.debug("panel.node_api.response %s", debug_json({"url": url, "status": int(response.status), "body": data}))
                if not (200 <= int(response.status) < 300):
                    attempts.append(f"{url} returned HTTP {response.status}")
                    continue
                if path == "/config/apply" and data.get("ok") is False:
                    errors = data.get("errors") if isinstance(data.get("errors"), list) else []
                    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
                    listener_errors = [
                        str(item.get("error"))
                        for item in summary.get("listeners", [])
                        if isinstance(item, dict) and item.get("status") == "error" and item.get("error")
                    ]
                    details = errors or listener_errors or [str(data.get("message") or "Node rejected the routing configuration.")]
                    raise NodeAPIError("Node rejected routing config: " + " | ".join(details[:4]))
                return data
        except HTTPError as exc:
            if exc.code == 404 and path == "/config/apply":
                raise NodeAPIError(
                    "This node does not support configuration apply yet. Update the node service and restart it."
                ) from exc
            raise NodeAPIError(f"Node returned HTTP {exc.code} while handling {path}.") from exc
        except (RemoteDisconnected, URLError, TimeoutError, OSError, ssl.SSLError, ValueError, json.JSONDecodeError) as exc:
            attempts.append(f"{url} failed: {exc}")
            continue
    raise NodeAPIError(
        "Node API is unreachable while applying configuration. "
        "Check that the API port points to the node control-plane and that TLS/certificate settings match the node service. "
        f"Attempts: {_format_attempts(attempts)}"
    )



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
    request_body = b""
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
        logger.exception(
            "unhandled request error: %s %s elapsed_ms=%s", request.method, request.url.path, elapsed_ms
        )
        raise
    for key, value in SECURITY_HEADERS.items():
        response.headers[key] = value
    response.headers["X-Doctor-Dev"] = APP_TITLE
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if request.url.path.startswith("/api/") or request.url.path == "/health":
        logger.info(
            "%s %s -> %s %.2fms", request.method, request.url.path, response.status_code, elapsed_ms
        )
    if debug:
        logger.debug(
            "panel.request.end %s",
            debug_json({
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "elapsed_ms": elapsed_ms,
                "response_headers": redact_headers(response.headers),
            }),
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
        "nodes_total": len(nodes),
        "nodes_enabled": len([node for node in nodes if node.get("enabled")]),
        "message": "Panel is ready.",
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


@app.get("/api/panel/integrity")
async def panel_integrity(user: str = Depends(require_admin)) -> dict:
    return inspect_integrity()


@app.post("/api/panel/repair")
async def panel_repair(user: str = Depends(require_admin)) -> dict:
    result = repair_integrity()
    logger.warning("data integrity repair executed by=%s changes=%s", user, result.get("changes"))
    return result


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
    node_id = require_node_id(node_id)
    node = update_node(node_id, body.model_dump())
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    return {"ok": True, "node": node}


@app.delete("/api/nodes/{node_id}")
async def api_delete_node(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    if not remove_node(node_id):
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    disabled_cores = disable_cores_for_node(
        node_id,
        error="This core was disabled because its linked node was deleted.",
    )
    logger.warning("node deleted: node_id=%s by=%s disabled_cores=%s", node_id, user, len(disabled_cores))
    return {"ok": True, "disabled_cores": disabled_cores}


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
    node_id = require_node_id(node_id)
    node = get_node(node_id)
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
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


@app.post("/api/cores/advanced/validate")
async def api_validate_advanced_config(
    body: AdvancedConfigValidateBody, user: str = Depends(require_admin)
) -> dict:
    result = validate_manual_json_config(body.json_config)
    return {"ok": True, **result}






def _validate_core_forwarding_topology(body: CoreBody) -> None:
    local_hosts = {"", "127.0.0.1", "localhost", "::1", "0.0.0.0", "[::1]"}
    balancers = {b.alias: b for b in body.balancers if b.enabled}
    errors: list[str] = []

    def local_self(host: str, port: int, inbound) -> bool:
        fixed = set(int(p) for p in inbound.fixed_ports or [])
        if port not in fixed:
            return False
        host_l = str(host or "").strip().lower()
        bind_l = str(inbound.bind_ip or "0.0.0.0").strip().lower()
        public_l = str(inbound.public_host or "").strip().lower()
        return host_l in local_hosts or host_l == bind_l or (public_l and host_l == public_l)

    for inbound in body.inbounds:
        if not inbound.enabled:
            continue
        if inbound.port_mode == "fixed" and not inbound.fixed_ports:
            errors.append(f"{inbound.name}: choose at least one listen port.")
        if inbound.target_type == "static":
            if local_self(inbound.target_host, int(inbound.target_port), inbound):
                errors.append(
                    f"{inbound.name}: target points back to the same inbound port. "
                    "Use the real upstream host/port, not the listen port."
                )
        elif inbound.target_type == "balancer":
            balancer = balancers.get(inbound.target_balancer)
            if not balancer:
                errors.append(f"{inbound.name}: selected balancer does not exist or is disabled.")
                continue
            enabled_endpoints = [e for e in balancer.endpoints if e.enabled]
            if not enabled_endpoints:
                errors.append(f"{inbound.name}: selected balancer has no enabled endpoint.")
            for endpoint in enabled_endpoints:
                if endpoint.type == "static" and local_self(endpoint.host, int(endpoint.port), inbound):
                    errors.append(
                        f"{inbound.name}: balancer endpoint {endpoint.host}:{endpoint.port} "
                        "points back to this inbound listener."
                    )
    if errors:
        raise api_error(400, "INVALID_FORWARDING_TOPOLOGY", " | ".join(errors[:6]))

def _validate_core_advanced_config(body: CoreBody) -> None:
    adv = body.advanced_config
    if not adv or not adv.enabled:
        return
    result = validate_manual_json_config(adv.json_config)
    if not result.get("valid"):
        message = "; ".join(result.get("errors") or ["Advanced JSON is invalid."])
        raise api_error(400, "INVALID_ADVANCED_JSON", message)


@app.post("/api/cores")
async def api_create_core(body: CoreBody, user: str = Depends(require_admin)) -> dict:
    if not is_valid_node_id(body.node_id):
        raise api_error(400, "INVALID_NODE_ID", "Select a valid node before creating a core.")
    if not get_node(body.node_id):
        raise api_error(400, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    _validate_core_advanced_config(body)
    _validate_core_forwarding_topology(body)
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
    core_id = require_core_id(core_id)
    if not is_valid_node_id(body.node_id):
        raise api_error(400, "INVALID_NODE_ID", "Select a valid node before saving this core.")
    if not get_node(body.node_id):
        raise api_error(400, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    _validate_core_advanced_config(body)
    _validate_core_forwarding_topology(body)
    core = update_core(core_id, body.model_dump())
    if not core:
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
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
    core_id = require_core_id(core_id)
    if not remove_core(core_id):
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
    logger.info("core deleted: id=%s by=%s", core_id, user)
    return {"ok": True}


@app.get("/api/cores/{core_id}/preview")
async def api_core_preview(core_id: str, user: str = Depends(require_admin)) -> dict:
    core_id = require_core_id(core_id)
    core = get_core(core_id)
    if not core:
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
    return {
        "ok": True,
        "core": core,
        "node_config_preview": build_node_config(str(core.get("node_id"))),
    }


@app.get("/api/nodes/{node_id}/inbounds")
async def api_node_inbounds(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    if not get_node(node_id):
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    return {"ok": True, "inbounds": inbound_catalog(node_id)}


@app.get("/api/nodes/{node_id}/config-preview")
async def api_node_config_preview(
    node_id: str, user: str = Depends(require_admin)
) -> dict:
    node_id = require_node_id(node_id)
    if not get_node(node_id):
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    return {"ok": True, "config": build_node_config(node_id)}



@app.post("/api/nodes/{node_id}/apply-config")
async def api_apply_node_config(node_id: str, user: str = Depends(require_admin)) -> dict:
    node_id = require_node_id(node_id)
    node = get_node(node_id)
    if not node:
        raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
    payload = build_node_config(node_id)
    try:
        data = await asyncio.to_thread(_post_node_api, node, "/config/apply", payload)
        changed = set_node_cores_apply_result(node_id, ok=True)
        logger.info("node config applied: node_id=%s cores=%s by=%s", node_id, len(payload.get("cores", [])), user)
        return {
            "ok": True,
            "message": f"Applied {len(payload.get('cores', []))} core configuration(s) to {node.get('name') or node.get('address')}.",
            "node_response": data,
            "updated_cores": changed,
        }
    except NodeAPIError as exc:
        set_node_cores_apply_result(node_id, ok=False, error=str(exc))
        logger.warning("node config apply failed: node_id=%s error=%s", node_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/cores/{core_id}/apply")
async def api_apply_core(core_id: str, user: str = Depends(require_admin)) -> dict:
    core_id = require_core_id(core_id)
    core = get_core(core_id)
    if not core:
        raise api_error(404, "CORE_NOT_FOUND", "The selected core no longer exists. Refresh the page.")
    node_id = str(core.get("node_id") or "")
    node = get_node(node_id)
    if not node:
        set_core_apply_result(core_id, ok=False, error="Selected node does not exist.")
        raise api_error(400, "NODE_NOT_FOUND", "The node linked to this core no longer exists. Run Repair Data or select another node.")
    payload = build_node_config(node_id)
    try:
        data = await asyncio.to_thread(_post_node_api, node, "/config/apply", payload)
        updated = set_core_apply_result(core_id, ok=True)
        logger.info("core applied: core_id=%s node_id=%s by=%s", core_id, node_id, user)
        return {"ok": True, "message": "Core configuration was applied successfully.", "core": updated, "node_response": data}
    except NodeAPIError as exc:
        updated = set_core_apply_result(core_id, ok=False, error=str(exc))
        logger.warning("core apply failed: core_id=%s node_id=%s error=%s", core_id, node_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
        node_id = require_node_id(node_id)
        node = get_node(node_id)
        if not node:
            raise api_error(404, "NODE_NOT_FOUND", "The selected node no longer exists. Refresh the page.")
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
        except NodeAPIError as exc:
            logger.warning("cannot read node logs: node_id=%s error=%s", node_id, exc)
            return {
                "ok": False,
                "source": source,
                "node": node,
                "lines": [],
                "error": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("cannot read node logs: node_id=%s unexpected=%s", node_id, exc)
            return {
                "ok": False,
                "source": source,
                "node": node,
                "lines": [],
                "error": "Unexpected node log error. Check panel logs for details.",
            }
    raise HTTPException(status_code=400, detail="Unknown log source.")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": APP_TITLE, "version": __version__}
