from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

app = FastAPI(title="Doctor Dev Node", version=__version__, docs_url=None, redoc_url=None)
logger = logging.getLogger("doctor_dev_node.server")


def api_key() -> str:
    return os.getenv("API_KEY", "")


def check_auth(authorization: str | None) -> None:
    key = api_key()
    if not key:
        return
    if authorization != f"Bearer {key}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


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


def runtime_summary() -> dict[str, Any]:
    cfg = read_routing_config()
    cores = cfg.get("cores") if isinstance(cfg.get("cores"), list) else []
    inbounds = []
    balancers = []
    for core in cores:
        if isinstance(core, dict):
            for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                if isinstance(inbound, dict):
                    inbounds.append({"core": core.get("name"), **inbound})
            for balancer in core.get("balancers", []) if isinstance(core.get("balancers"), list) else []:
                if isinstance(balancer, dict):
                    balancers.append({"core": core.get("name"), **balancer})
    return {
        "cores_total": len(cores),
        "inbounds_total": len(inbounds),
        "balancers_total": len(balancers),
        "generated_at": cfg.get("generated_at"),
        **runtime.summary(),
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
    generated_at: str | None = None
    cores: list[dict[str, Any]] = []


@app.get("/health")
async def health() -> dict:
    logger.info("health check requested")
    return {
        "status": "ok",
        "app": "Doctor Dev Node",
        "version": __version__,
        "control_plane": {
            "host": os.getenv("NODE_HOST", "127.0.0.1"),
            "api_port": int(os.getenv("API_PORT", "62051")),
            "tls": bool(os.getenv("SSL_CERT_FILE") and os.getenv("SSL_KEY_FILE")),
        },
        "data_plane": {
            "service_port": int(os.getenv("SERVICE_PORT", "62050")),
            "service_protocol": os.getenv("SERVICE_PROTOCOL", "grpc"),
        },
    }


@app.get("/status")
async def status(authorization: str | None = Header(default=None)) -> dict:
    check_auth(authorization)
    logger.info("status requested")
    if is_debug_enabled():
        logger.debug("node.status.env %s", debug_json({"NODE_HOST": os.getenv("NODE_HOST"), "API_PORT": os.getenv("API_PORT"), "SERVICE_PORT": os.getenv("SERVICE_PORT"), "SERVICE_PROTOCOL": os.getenv("SERVICE_PROTOCOL"), "SSL_CERT_FILE": os.getenv("SSL_CERT_FILE"), "SSL_KEY_FILE": "***" if os.getenv("SSL_KEY_FILE") else ""}))
    return {
        "status": "running",
        "version": __version__,
        "config": {
            "node_host": os.getenv("NODE_HOST", "127.0.0.1"),
            "api_port": int(os.getenv("API_PORT", "62051")),
            "service_port": int(os.getenv("SERVICE_PORT", "62050")),
            "service_protocol": os.getenv("SERVICE_PROTOCOL", "grpc"),
            "ssl_cert_file": os.getenv("SSL_CERT_FILE", ""),
            "ssl_key_file": "***" if os.getenv("SSL_KEY_FILE") else "",
        },
        "routing": runtime_summary(),
    }


@app.get("/config")
async def get_config(authorization: str | None = Header(default=None)) -> dict:
    check_auth(authorization)
    logger.info("config requested")
    return {"ok": True, "config": read_routing_config(), "summary": runtime_summary()}


@app.get("/logs")
async def logs(limit: int = 300, level: str = "all", q: str = "", authorization: str | None = Header(default=None)) -> dict:
    check_auth(authorization)
    path = node_log_file()
    lines = filter_lines(tail_file(path, limit=max(limit, 1)), level=level, query=q)
    return {"ok": True, "source": "node", "path": str(path), "limit": limit, "level": level, "query": q, "lines": lines[-limit:]}


@app.post("/config/apply")
async def apply_config(body: ApplyConfigBody, authorization: str | None = Header(default=None)) -> dict:
    check_auth(authorization)
    data = body.model_dump()
    if is_debug_enabled():
        logger.debug("node.apply.received %s", debug_json(data))
    data["applied_at"] = now()
    write_routing_config(data)
    summary = await runtime.apply_config(data)
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
    protocol = os.getenv("SERVICE_PROTOCOL", "grpc").lower()
    if protocol not in {"grpc", "rest"}:
        raise SystemExit("SERVICE_PROTOCOL must be grpc or rest")
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
