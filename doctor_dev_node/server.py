from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException

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


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": "Doctor Dev Node",
        "version": __version__,
        "node_host": os.getenv("NODE_HOST", "127.0.0.1"),
        "service_port": int(os.getenv("SERVICE_PORT", "62050")),
        "service_protocol": os.getenv("SERVICE_PROTOCOL", "grpc"),
    }


@app.get("/status")
async def status(authorization: str | None = Header(default=None)) -> dict:
    check_auth(authorization)
    return {
        "status": "running",
        "version": __version__,
        "config": {
            "node_host": os.getenv("NODE_HOST", "127.0.0.1"),
            "service_port": int(os.getenv("SERVICE_PORT", "62050")),
            "service_protocol": os.getenv("SERVICE_PROTOCOL", "grpc"),
            "ssl_cert_file": os.getenv("SSL_CERT_FILE", ""),
            "ssl_key_file": "***" if os.getenv("SSL_KEY_FILE") else "",
        },
        "note": "Runtime forwarding logic is not attached yet.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Doctor Dev Node server")
    parser.add_argument("--env", default=os.getenv("DOCTOR_DEV_NODE_ENV", ".env"), help="node environment file")
    parser.add_argument("--host", default=None, help="override bind host")
    parser.add_argument("--port", type=int, default=None, help="override service port")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.env and Path(args.env).exists():
        load_env_file(args.env)
    host = args.host or os.getenv("NODE_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("SERVICE_PORT", "62050"))
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
