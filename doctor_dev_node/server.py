from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi import Request as FastAPIRequest
from pydantic import BaseModel

from . import __version__
from .env_loader import load_env_file
from .logging_utils import (
    body_preview,
    debug_json,
    filter_lines,
    is_debug_enabled,
    node_log_file,
    redact_headers,
    setup_node_logging,
    tail_file,
)
from .runtime import runtime
from .peer_tokens import verify_peer_token

app = FastAPI(title="Doctor Dev Node", version=__version__, docs_url=None, redoc_url=None)
logger = logging.getLogger("doctor_dev_node.server")


def pydantic_to_dict(model: object) -> dict:
    """Return a plain dict from Pydantic v1 or v2 models."""
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    if hasattr(model, "dict"):
        return model.dict()  # type: ignore[attr-defined]
    return dict(model)  # type: ignore[arg-type]


def api_key() -> str:
    return os.getenv("API_KEY", "")


def _auth_error(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"ok": False, "code": code, "message": message})


def check_auth(authorization: Optional[str]) -> None:
    key = api_key()
    if not key:
        return
    if authorization != f"Bearer {key}":
        raise _auth_error("INVALID_NODE_API_KEY", "Invalid or missing node API key.")


def _enabled_cores_from_config(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    cores = cfg.get("cores") if isinstance(cfg.get("cores"), list) else []
    return [core for core in cores if isinstance(core, dict) and core.get("enabled") is not False]


def _active_core_from_config(cfg: dict[str, Any]) -> Optional[dict[str, Any]]:
    enabled = _enabled_cores_from_config(cfg)
    return enabled[0] if enabled else None


def check_export_auth(authorization: Optional[str], x_doctor_node_token: Optional[str]) -> str:
    key = api_key()
    if key and authorization == f"Bearer {key}":
        return "panel_api_key"

    cfg = read_routing_config()
    secret = str(cfg.get("peer_verify_secret") or "")
    target_node_id = str(cfg.get("node_id") or os.getenv("NODE_ID", ""))
    active_core = _active_core_from_config(cfg)
    target_core_id = str((active_core or {}).get("id") or "")

    if x_doctor_node_token:
        if not secret:
            logger.warning("node export rejected: peer token supplied but peer_verify_secret is missing")
            raise _auth_error("PEER_SECRET_MISSING", "Peer token auth is not configured on this node.")
        try:
            verify_peer_token(
                x_doctor_node_token,
                secret=secret,
                target_node_id=target_node_id,
                target_core_id=target_core_id,
            )
            return "peer_token"
        except Exception as exc:  # noqa: BLE001
            logger.warning("node export rejected: peer token failed: %s", exc)
            raise _auth_error("INVALID_PEER_TOKEN", f"Invalid peer token: {exc}")

    if not key and not secret:
        return "open_dev_no_auth"

    if authorization:
        logger.warning("node export rejected: invalid Authorization header")
        raise _auth_error("INVALID_NODE_API_KEY", "Invalid node API key for runtime export.")
    raise _auth_error("MISSING_NODE_EXPORT_AUTH", "Missing node runtime export auth. Send Authorization: Bearer <API_KEY> or X-Doctor-Node-Token.")


def node_data_dir() -> Path:
    path = Path(os.getenv("DOCTOR_DEV_NODE_DATA_DIR", "/var/lib/doctor-node")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def routing_config_path() -> Path:
    configured = os.getenv("DOCTOR_DEV_NODE_ROUTING_CONFIG", "").strip()
    if configured:
        return Path(configured).expanduser()
    return node_data_dir() / "routing-config.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_env(*names: str, default: int) -> int:
    for name in names:
        value = os.getenv(name)
        if value is None or str(value).strip() == "":
            continue
        try:
            return int(str(value).strip())
        except ValueError:
            continue
    return int(default)


def api_identity() -> dict[str, Any]:
    """Return the actual API bind identity for the running node process.

    `main.py` and `doctor_dev_node.server:main` set DOCTOR_DEV_NODE_BOUND_*
    from CLI overrides before the ASGI app is imported. These values are the
    source of truth for self-reporting, while NODE_HOST/API_PORT remain
    backwards-compatible aliases.
    """
    host = os.getenv("DOCTOR_DEV_NODE_BOUND_HOST") or os.getenv("NODE_HOST") or "127.0.0.1"
    port = _int_env("DOCTOR_DEV_NODE_BOUND_API_PORT", "API_PORT", default=62051)
    tls = bool(os.getenv("SSL_CERT_FILE") and os.getenv("SSL_KEY_FILE"))
    return {
        "host": host,
        "port": port,
        "api_port": port,
        "tls": tls,
    }


def read_routing_config() -> dict[str, Any]:
    path = routing_config_path()
    if not path.exists():
        if is_debug_enabled():
            logger.debug("node.config.read missing path=%s", path)
        return {"version": 1, "generated_at": None, "cores": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if is_debug_enabled():
            logger.debug("node.config.read %s", debug_json({"path": str(path), "config": data}))
        return data
    except Exception as exc:  # noqa: BLE001
        return {"version": 1, "error": f"Cannot read routing config: {exc}", "cores": []}


def write_routing_config(data: dict[str, Any]) -> None:
    path = routing_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="routing.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        if is_debug_enabled():
            logger.debug("node.config.write %s", debug_json({"path": str(path), "config": data}))
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _config_hash(cfg: dict[str, Any]) -> str:
    material = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def runtime_summary() -> dict[str, Any]:
    cfg = read_routing_config()
    cores = cfg.get("cores") if isinstance(cfg.get("cores"), list) else []
    active_core = _active_core_from_config(cfg)
    inbounds = []
    balancers = []
    for core in cores:
        if isinstance(core, dict):
            for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                if isinstance(inbound, dict):
                    inbounds.append({"core_id": core.get("id"), "core_name": core.get("name"), **inbound})
            for balancer in core.get("balancers", []) if isinstance(core.get("balancers"), list) else []:
                if isinstance(balancer, dict):
                    balancers.append({"core_id": core.get("id"), "core_name": core.get("name"), **balancer})
    return {
        "node_id": cfg.get("node_id") or os.getenv("NODE_ID", ""),
        "config_hash": _config_hash(cfg),
        "cores_total": len(cores),
        "enabled_cores_total": len(_enabled_cores_from_config(cfg)),
        "core": {
            "id": (active_core or {}).get("id", ""),
            "name": (active_core or {}).get("name", ""),
            "enabled": bool(active_core) and (active_core or {}).get("enabled") is not False,
        },
        "inbounds_total": len(inbounds),
        "balancers_total": len(balancers),
        "generated_at": cfg.get("generated_at"),
        "applied_at": cfg.get("applied_at"),
        "desired_inbounds": inbounds,
        "desired_balancers": balancers,
        **runtime.summary(),
    }


def runtime_payload(*, auth_source: str = "") -> dict[str, Any]:
    cfg = read_routing_config()
    summary = runtime_summary()
    listeners = summary.get("listeners") if isinstance(summary.get("listeners"), list) else []
    return {
        "ok": True,
        "source": "node-runtime",
        "auth_source": auth_source,
        "node_id": cfg.get("node_id") or os.getenv("NODE_ID", ""),
        "generated_at": cfg.get("generated_at"),
        "exported_at": now(),
        "api": api_identity(),
        "core": summary.get("core") or {},
        "summary": summary,
        "listeners": listeners,
    }



async def _capture_request_body(request: FastAPIRequest) -> bytes:
    body = await request.body()

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]
    return body


@app.middleware("http")
async def debug_request_logging(request: FastAPIRequest, call_next):
    started = time.perf_counter()
    debug = is_debug_enabled()
    if debug:
        try:
            body = await _capture_request_body(request)
            logger.debug(
                "node.request.start %s",
                debug_json({
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query or ""),
                    "client": request.client.host if request.client else "",
                    "headers": redact_headers(request.headers),
                    "body": body_preview(body),
                }),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("node.request.capture_failed method=%s path=%s error=%s", request.method, request.url.path, exc)
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception("node.request.error method=%s path=%s elapsed_ms=%s", request.method, request.url.path, elapsed_ms)
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info("%s %s -> %s %.2fms", request.method, request.url.path, response.status_code, elapsed_ms)
    if debug:
        logger.debug(
            "node.request.end %s",
            debug_json({
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "elapsed_ms": elapsed_ms,
                "response_headers": redact_headers(response.headers),
            }),
        )
    return response


class ApplyConfigBody(BaseModel):
    version: int = 1
    node_id: str = ""
    generated_at: Optional[str] = None
    cores: list[dict[str, Any]] = []


@app.get("/health")
async def health() -> dict:
    logger.info("health check requested")
    summary = runtime.summary()
    return {
        "status": "ok",
        "app": "Doctor Dev Node",
        "version": __version__,
        "api": api_identity(),
        "runtime": {
            "active": bool(summary.get("runtime_active")),
            "listeners_total": int(summary.get("listeners_total") or 0),
            "last_error": summary.get("last_error") or "",
        },
    }


@app.get("/status")
async def status(authorization: Optional[str] = Header(default=None)) -> dict:
    check_auth(authorization)
    logger.info("status requested")
    if is_debug_enabled():
        logger.debug("node.status.env %s", debug_json({"NODE_HOST": os.getenv("NODE_HOST"), "API_PORT": os.getenv("API_PORT"), "SSL_CERT_FILE": os.getenv("SSL_CERT_FILE"), "SSL_KEY_FILE": "***" if os.getenv("SSL_KEY_FILE") else ""}))
    return {
        "status": "running",
        "version": __version__,
        "config": {
            "node_host": api_identity()["host"],
            "api_port": api_identity()["port"],
            "ssl_cert_file": os.getenv("SSL_CERT_FILE", ""),
            "ssl_key_file": "***" if os.getenv("SSL_KEY_FILE") else "",
            "peer_token_auth": bool(read_routing_config().get("peer_verify_secret")),
        },
        "routing": runtime_summary(),
    }


@app.get("/config")
async def get_config(authorization: Optional[str] = Header(default=None)) -> dict:
    check_auth(authorization)
    logger.info("config requested")
    return {"ok": True, "config": read_routing_config(), "summary": runtime_summary()}



@app.get("/runtime")
async def get_runtime(
    authorization: Optional[str] = Header(default=None),
    x_doctor_node_token: Optional[str] = Header(default=None, alias="X-Doctor-Node-Token"),
) -> dict:
    """Return the live desired/actual node runtime state."""
    auth_source = check_export_auth(authorization, x_doctor_node_token)
    return runtime_payload(auth_source=auth_source)


@app.get("/config/export")
async def export_config(
    authorization: Optional[str] = Header(default=None),
    x_doctor_node_token: Optional[str] = Header(default=None, alias="X-Doctor-Node-Token"),
) -> dict:
    """Backward-compatible alias for /runtime."""
    auth_source = check_export_auth(authorization, x_doctor_node_token)
    payload = runtime_payload(auth_source=auth_source)
    payload["source"] = "node-runtime-export"
    return payload


@app.get("/logs")
async def logs(limit: int = 300, level: str = "all", q: str = "", authorization: Optional[str] = Header(default=None)) -> dict:
    check_auth(authorization)
    path = node_log_file()
    lines = filter_lines(tail_file(path, limit=max(limit, 1)), level=level, query=q)
    return {"ok": True, "source": "node", "path": str(path), "limit": limit, "level": level, "query": q, "lines": lines[-limit:]}


@app.post("/config/apply")
async def apply_config(body: ApplyConfigBody, authorization: Optional[str] = Header(default=None)) -> dict:
    check_auth(authorization)
    data = pydantic_to_dict(body)
    enabled_cores = [core for core in (data.get("cores") or []) if isinstance(core, dict) and core.get("enabled") is not False]
    if len(enabled_cores) > 1:
        logger.warning("routing config rejected: node_id=%s enabled_cores=%s", data.get("node_id"), len(enabled_cores))
        return {
            "ok": False,
            "message": "Node config is invalid: each node can have only one enabled core.",
            "errors": ["Each node can have only one enabled core."],
            "summary": runtime.summary() | {"ok": False, "listener_errors": 1},
        }
    if is_debug_enabled():
        logger.debug("node.apply.received %s", debug_json(data))
    data["applied_at"] = now()
    validation_errors = runtime.validate_config(data)
    if validation_errors:
        logger.warning("routing config rejected: node_id=%s errors=%s", data.get("node_id"), validation_errors)
        return {
            "ok": False,
            "message": "Routing config is invalid and was not applied.",
            "errors": validation_errors,
            "summary": runtime.summary() | {"ok": False, "listener_errors": len(validation_errors)},
        }
    summary = await runtime.apply_config(data)
    if not summary.get("ok", True):
        logger.warning("routing config apply finished with errors: node_id=%s summary=%s", data.get("node_id"), summary)
        return {
            "ok": False,
            "message": summary.get("last_error") or "Routing config could not start any listener.",
            "errors": summary.get("errors") or [],
            "summary": summary,
        }
    write_routing_config(data)
    logger.info("routing config applied: node_id=%s cores=%s listeners=%s", data.get("node_id"), len(data.get("cores") or []), summary.get("listeners_total"))
    return {"ok": True, "message": "Routing config saved and runtime reloaded on node.", "summary": runtime_summary()}



@app.on_event("startup")
async def _startup_runtime() -> None:
    # Re-activate the last applied routing config after service restart.
    try:
        cfg = read_routing_config()
        if cfg.get("cores"):
            await runtime.apply_config(cfg)
            logger.info("runtime restored from saved routing config")
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime restore failed: %s", exc)


@app.on_event("shutdown")
async def _shutdown_runtime() -> None:
    await runtime.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Doctor Dev Node control-plane server")
    parser.add_argument("--env", default=os.getenv("DOCTOR_DEV_NODE_ENV", ".env"), help="node environment file")
    parser.add_argument("--host", default=None, help="override API bind host")
    parser.add_argument("--port", type=int, default=None, help="override API port")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.env and Path(args.env).exists():
        load_env_file(args.env)
    log_path = setup_node_logging()
    logger.info("starting node server env=%s log=%s debug=%s", args.env, log_path, is_debug_enabled())
    host = args.host or os.getenv("NODE_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("API_PORT", "62051"))
    os.environ["NODE_HOST"] = str(host)
    os.environ["API_PORT"] = str(port)
    os.environ["DOCTOR_DEV_NODE_BOUND_HOST"] = str(host)
    os.environ["DOCTOR_DEV_NODE_BOUND_API_PORT"] = str(port)
    ssl_cert = os.getenv("SSL_CERT_FILE") or None
    ssl_key = os.getenv("SSL_KEY_FILE") or None
    use_tls = bool(ssl_cert and ssl_key)
    uvicorn.run(
        "doctor_dev_node.server:app",
        host=host,
        port=port,
        log_level="debug" if is_debug_enabled() else os.getenv("UVICORN_LOG_LEVEL", "info"),
        ssl_certfile=ssl_cert if use_tls else None,
        ssl_keyfile=ssl_key if use_tls else None,
    )


if __name__ == "__main__":
    main()




