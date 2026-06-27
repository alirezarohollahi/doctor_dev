#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from doctor_dev_panel.env_loader import load_env_file
from doctor_dev_panel.logging_utils import setup_panel_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Doctor Dev Panel server")
    parser.add_argument("--env", default=os.getenv("DOCTOR_DEV_ENV", ".env"), help="environment file path")
    parser.add_argument("--host", default=None, help="override bind host")
    parser.add_argument("--port", type=int, default=None, help="override bind port")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.env and Path(args.env).exists():
        load_env_file(args.env)

    host = args.host or os.getenv("HOST", "0.0.0.0")
    port = args.port or int(os.getenv("PORT", "8080"))
    log_path = setup_panel_logging()
    log_level = os.getenv("UVICORN_LOG_LEVEL", "info")
    print(f"Doctor Dev Panel log file: {log_path}")

    ssl_cert = os.getenv("SSL_CERT_PATH") or None
    ssl_key = os.getenv("SSL_KEY_PATH") or None
    use_tls = os.getenv("USE_TLS", "0") == "1" and ssl_cert and ssl_key

    uvicorn.run(
        "doctor_dev_panel.app:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=os.getenv("APP_ENV") == "development",
        ssl_certfile=ssl_cert if use_tls else None,
        ssl_keyfile=ssl_key if use_tls else None,
    )


if __name__ == "__main__":
    main()
