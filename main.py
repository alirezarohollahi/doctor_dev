#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable, Optional

import uvicorn

from doctor_dev_panel.env_loader import load_env_file


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_NODE_MODES = {"node", "doctor-node", "doctor-dev-node", "agent", "worker"}
_PANEL_MODES = {"panel", "doctor-panel", "doctor-dev-panel", "admin", "web"}
_MODE_ENV_NAMES = (
    "DOCTOR_DEV_MODE",
    "DOCTOR_DEV_ROLE",
    "APP_MODE",
    "APP_ROLE",
    "SERVICE_MODE",
    "SERVICE_ROLE",
    "RUN_MODE",
)


def _env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _env_flag(*names: str, default: bool = False) -> bool:
    value = _env_value(*names)
    if not value:
        return default
    return value.lower() in _TRUE_VALUES


def _normalize_mode(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-")
    if not normalized or normalized == "auto":
        return None
    if normalized in _NODE_MODES:
        return "node"
    if normalized in _PANEL_MODES:
        return "panel"
    raise SystemExit(
        "Invalid mode. Use DOCTOR_DEV_MODE=panel or DOCTOR_DEV_MODE=node "
        "or pass --mode panel|node."
    )


def _first_existing_path(paths: Iterable[Optional[str]]) -> Optional[Path]:
    for raw in paths:
        if not raw:
            continue
        path = Path(str(raw)).expanduser()
        if path.exists():
            return path
    return None


def _mode_hint() -> Optional[str]:
    for name in _MODE_ENV_NAMES:
        mode = _normalize_mode(os.getenv(name))
        if mode:
            return mode
    return None


def _load_environment(args: argparse.Namespace) -> Optional[Path]:
    # The installer/service still passes --env for the panel. That remains the
    # strongest source, so doctor_dev.sh and existing systemd units keep working.
    if args.env:
        env_path = Path(args.env).expanduser()
        if env_path.exists():
            load_env_file(env_path)
            return env_path
        return None

    # If the deployment platform sets a role before startup, prefer the matching
    # env-file variable. Otherwise fall back to the old generic .env behavior.
    mode = _mode_hint()
    if mode == "node":
        candidates = (
            os.getenv("DOCTOR_DEV_NODE_ENV"),
            os.getenv("DOCTOR_DEV_NODE_ENV_FILE"),
            os.getenv("DOCTOR_DEV_ENV"),
            ".env",
            "node.env",
        )
    elif mode == "panel":
        candidates = (
            os.getenv("DOCTOR_DEV_PANEL_ENV"),
            os.getenv("DOCTOR_DEV_PANEL_ENV_FILE"),
            os.getenv("DOCTOR_DEV_ENV"),
            ".env",
            "panel.env",
        )
    else:
        candidates = (
            os.getenv("DOCTOR_DEV_ENV"),
            os.getenv("DOCTOR_DEV_PANEL_ENV"),
            os.getenv("DOCTOR_DEV_PANEL_ENV_FILE"),
            os.getenv("DOCTOR_DEV_NODE_ENV"),
            os.getenv("DOCTOR_DEV_NODE_ENV_FILE"),
            ".env",
        )

    env_path = _first_existing_path(candidates)
    if env_path:
        load_env_file(env_path)
    return env_path


def _current_mode(cli_mode: Optional[str]) -> str:
    cli = _normalize_mode(cli_mode)
    if cli:
        return cli
    env = _mode_hint()
    if env:
        return env
    return "panel"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Doctor Dev entrypoint")
    parser.add_argument("--env", default=None, help="environment file path")
    parser.add_argument(
        "--mode",
        "--role",
        dest="mode",
        default=None,
        help="run mode: panel or node. Env alternative: DOCTOR_DEV_MODE=node|panel",
    )
    parser.add_argument("--host", default=None, help="override bind host")
    parser.add_argument("--port", type=int, default=None, help="override bind/API port")
    return parser


def run_panel(args: argparse.Namespace, env_path: Optional[Path]) -> None:
    from doctor_dev_panel.logging_utils import is_debug_enabled, setup_panel_logging

    host = args.host or os.getenv("HOST", "0.0.0.0")
    port = args.port or int(os.getenv("PORT", "8080"))
    log_path = setup_panel_logging()
    log_level = "debug" if is_debug_enabled() else os.getenv("UVICORN_LOG_LEVEL", "info")

    ssl_cert = os.getenv("SSL_CERT_PATH") or os.getenv("SSL_CERT_FILE") or None
    ssl_key = os.getenv("SSL_KEY_PATH") or os.getenv("SSL_KEY_FILE") or None
    use_tls = _env_flag("USE_TLS", default=False) and bool(ssl_cert and ssl_key)

    print(f"Doctor Dev mode: panel")
    print(f"Doctor Dev env file: {env_path or '(not loaded)'}")
    print(f"Doctor Dev Panel log file: {log_path}")

    uvicorn.run(
        "doctor_dev_panel.app:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=os.getenv("APP_ENV") == "development",
        ssl_certfile=ssl_cert if use_tls else None,
        ssl_keyfile=ssl_key if use_tls else None,
    )


def run_node(args: argparse.Namespace, env_path: Optional[Path]) -> None:
    from doctor_dev_node.logging_utils import is_debug_enabled, setup_node_logging

    host = args.host or os.getenv("NODE_HOST") or os.getenv("HOST", "127.0.0.1")
    port = args.port or int(os.getenv("API_PORT") or os.getenv("PORT") or "62051")
    # Node now exposes one management API port only. Listener/data ports are
    # created from inbound runtime config; SERVICE_PORT/SERVICE_PROTOCOL are legacy.
    # Keep the process environment consistent before Uvicorn imports the app in
    # its worker process. Without this, `python main.py --mode node --port 9098`
    # could listen on 9098 while /health still reported the stale env API_PORT.
    os.environ["NODE_HOST"] = str(host)
    os.environ["API_PORT"] = str(port)
    os.environ["DOCTOR_DEV_NODE_BOUND_HOST"] = str(host)
    os.environ["DOCTOR_DEV_NODE_BOUND_API_PORT"] = str(port)

    log_path = setup_node_logging()
    ssl_cert = os.getenv("SSL_CERT_FILE") or os.getenv("SSL_CERT_PATH") or None
    ssl_key = os.getenv("SSL_KEY_FILE") or os.getenv("SSL_KEY_PATH") or None
    use_tls = bool(ssl_cert and ssl_key)

    print(f"Doctor Dev mode: node")
    print(f"Doctor Dev env file: {env_path or '(not loaded)'}")
    print(f"Doctor Dev Node log file: {log_path}")

    uvicorn.run(
        "doctor_dev_node.server:app",
        host=host,
        port=port,
        log_level="debug" if is_debug_enabled() else os.getenv("UVICORN_LOG_LEVEL", "info"),
        ssl_certfile=ssl_cert if use_tls else None,
        ssl_keyfile=ssl_key if use_tls else None,
    )


def main() -> None:
    args = build_parser().parse_args()
    env_path = _load_environment(args)
    mode = _current_mode(args.mode)
    if mode == "node":
        run_node(args, env_path)
    else:
        run_panel(args, env_path)


if __name__ == "__main__":
    main()




