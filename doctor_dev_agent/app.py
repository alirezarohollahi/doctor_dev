from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query

from doctor_dev_shared.certificates import validate_certificate_ref
from doctor_dev_shared.models import ApplyResult, CertificateRef, GeneratedConfig
from .echo_server import start_echo_server
from .settings import AGENT_API_KEY, AGENT_HOST, AGENT_LOG_FILE, AGENT_PORT, CERT_DIR, ECHO_HOST, ECHO_PORTS, LAST_CONFIG_FILE, NODE_NAME, ensure_dirs
from .tunnel_engine import TunnelManager

app = FastAPI(title="Doctor Dev Agent", version="1.0.0")
_RUNTIME = {
    "active_connections": 0,
    "total_connections": 0,
    "bytes_in": 0,
    "bytes_out": 0,
    "last_applied_core_id": None,
    "last_applied_at": None,
}
_ECHO_SERVERS = []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_log(level: str, message: str) -> None:
    ensure_dirs()
    line = f"{now_iso()} [{level.upper()}] {NODE_NAME}: {message}\n"
    old = AGENT_LOG_FILE.read_text(encoding="utf-8") if AGENT_LOG_FILE.exists() else ""
    AGENT_LOG_FILE.write_text(old + line, encoding="utf-8")



def materialize_and_validate_tls(config: GeneratedConfig) -> list[str]:
    warnings: list[str] = []
    for inbound in config.inbounds:
        tls = inbound.get("tls", {}) or {}
        if not tls.get("enabled"):
            continue
        ref = CertificateRef.model_validate(tls)
        if ref.mode == "pasted_content" and ref.fullchain_content and ref.privkey_content:
            domain = ref.domain or ref.name or inbound.get("name") or "inline"
            safe_domain = "".join(ch for ch in domain.lower() if ch.isalnum() or ch in {"-", "."}).strip(".") or "inline"
            target_dir = CERT_DIR / safe_domain
            target_dir.mkdir(parents=True, exist_ok=True)
            fullchain_path = target_dir / "fullchain.pem"
            privkey_path = target_dir / "privkey.pem"
            fullchain_path.write_text(ref.fullchain_content, encoding="utf-8")
            privkey_path.write_text(ref.privkey_content, encoding="utf-8")
            ref.fullchain_path = str(fullchain_path)
            ref.privkey_path = str(privkey_path)
            tls["fullchain_path"] = ref.fullchain_path
            tls["privkey_path"] = ref.privkey_path
            warnings.append(f"TLS pasted content materialized for inbound={inbound.get('name')} at {target_dir}")
        result = validate_certificate_ref(ref, panel_can_read_paths=(ref.mode != "file_on_node"))
        if not result.ok:
            raise ValueError(f"TLS validation failed for inbound={inbound.get('name')}: {result.message}")
        warnings.extend([f"TLS warning inbound={inbound.get('name')}: {w}" for w in result.warnings])
        warnings.append(f"TLS metadata validated for inbound={inbound.get('name')} mode={ref.mode}; runtime TLS termination is enabled")
    return warnings

tunnel_manager = TunnelManager(write_log)


def require_agent_auth(authorization: str | None) -> None:
    if authorization != f"Bearer {AGENT_API_KEY}":
        raise HTTPException(status_code=401, detail="invalid or missing agent API key")


@app.on_event("startup")
async def startup() -> None:
    ensure_dirs()
    write_log("info", f"agent started on {AGENT_HOST}:{AGENT_PORT} version=1.0.0")
    for port in ECHO_PORTS:
        try:
            server = await start_echo_server(ECHO_HOST, port, write_log, label=NODE_NAME)
            _ECHO_SERVERS.append(server)
        except OSError as exc:
            write_log("warning", f"echo target not started on {ECHO_HOST}:{port}: {exc}")


@app.on_event("shutdown")
async def shutdown() -> None:
    await tunnel_manager.stop()
    for server in _ECHO_SERVERS:
        server.close()
    for server in _ECHO_SERVERS:
        await server.wait_closed()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "doctor_dev_agent", "node_name": NODE_NAME, "version": "1.0.0"}


@app.get("/api/status")
async def status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_auth(authorization)
    write_log("info", "status requested by panel")
    return {
        "ok": True,
        "node_name": NODE_NAME,
        "host": AGENT_HOST,
        "port": AGENT_PORT,
        "version": "1.0.0",
        "runtime": _RUNTIME,
        "tunnel": tunnel_manager.snapshot(),
        "echo_targets": [{"host": ECHO_HOST, "port": port} for port in ECHO_PORTS],
    }


@app.post("/api/apply")
async def apply_config(config: GeneratedConfig, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_auth(authorization)
    ensure_dirs()
    tls_warnings = materialize_and_validate_tls(config)
    LAST_CONFIG_FILE.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    _RUNTIME["last_applied_core_id"] = config.core_id
    _RUNTIME["last_applied_at"] = now_iso()
    try:
        warnings = tls_warnings + await tunnel_manager.apply(config.model_dump())
    except Exception as exc:  # noqa: BLE001
        write_log("error", f"apply failed core={config.core_name} error={exc}")
        raise HTTPException(status_code=400, detail=f"agent failed to apply runtime config: {exc}") from exc
    write_log("info", f"config applied core={config.core_name} core_id={config.core_id} inbounds={len(config.inbounds)} routes={len(config.routes)} listeners={tunnel_manager.snapshot()['running_listeners']}")
    return ApplyResult(
        ok=True,
        message="config applied by tls-aware runtime tunnel engine",
        node_id=config.node_id,
        core_id=config.core_id,
        saved_path=str(LAST_CONFIG_FILE),
        warnings=warnings,
    ).model_dump()


@app.post("/api/stop")
async def stop_runtime(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_auth(authorization)
    await tunnel_manager.stop()
    return {"ok": True, "message": "runtime tunnel listeners stopped"}


@app.get("/api/runtime")
async def runtime(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_auth(authorization)
    return {"ok": True, "node_name": NODE_NAME, "runtime": _RUNTIME, "tunnel": tunnel_manager.snapshot()}


@app.get("/api/logs")
async def logs(limit: int = Query(200, ge=1, le=2000), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_auth(authorization)
    ensure_dirs()
    if not AGENT_LOG_FILE.exists():
        return {"ok": True, "node_name": NODE_NAME, "lines": []}
    lines = AGENT_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"ok": True, "node_name": NODE_NAME, "lines": lines[-limit:]}
