from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import __version__
from .env_loader import load_env_file

app = FastAPI(title="Doctor Dev Node", version=__version__, docs_url=None, redoc_url=None)


def api_key() -> str:
    return os.getenv("API_KEY", "")


def check_auth(authorization: str | None) -> None:
    key = api_key()
    if not key:
        return
    if authorization != f"Bearer {key}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def node_data_dir() -> Path:
    path = Path(os.getenv("DOCTOR_DEV_NODE_DATA_DIR", "/var/lib/docter-node")).expanduser()
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
        return {"version": 1, "generated_at": None, "cores": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
        "runtime_active": False,
        "note": "Routing config storage is ready; high-performance forwarding runtime is not attached yet.",
    }


class ApplyConfigBody(BaseModel):
    version: int = 1
    node_id: str = ""
    generated_at: str | None = None
    cores: list[dict[str, Any]] = []


@app.get("/health")
async def health() -> dict:
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
    return {"ok": True, "config": read_routing_config(), "summary": runtime_summary()}


@app.post("/config/apply")
async def apply_config(body: ApplyConfigBody, authorization: str | None = Header(default=None)) -> dict:
    check_auth(authorization)
    data = body.model_dump()
    data["applied_at"] = now()
    write_routing_config(data)
    return {"ok": True, "message": "Routing config saved on node.", "summary": runtime_summary()}


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
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
        ssl_certfile=ssl_cert if use_tls else None,
        ssl_keyfile=ssl_key if use_tls else None,
    )


if __name__ == "__main__":
    main()
