from __future__ import annotations

import base64
import difflib
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from doctor_dev_shared.certificates import certificate_ref_from_request, validate_certificate_ref
from doctor_dev_shared.config_builder import build_generated_config, dry_run_summary
from doctor_dev_shared.models import (
    BalancerType,
    CertificateCreate,
    CertificateMode,
    CertificateRef,
    CertificateValidationRequest,
    CoreCreate,
    CoreOut,
    InboundConfig,
    InboundLimits,
    InboundListener,
    NodeAdvancedSettings,
    NodeCreate,
    NodeOut,
    RouteConfig,
    RouteTarget,
    TargetType,
)
from .agent_client import apply_config, check_agent_status, fetch_logs, fetch_runtime, stop_runtime
from .network_tools import tcp_roundtrip, tls_roundtrip
from .settings import CERT_DIR, CONFIG_DIR, ensure_dirs
from .store import store
from .ui import FRONTEND_HTML

app = FastAPI(title="Doctor Dev Panel", version="1.0.0")

SESSION_COOKIE = "doctor_dev_panel_session"
AUTH_PUBLIC_PATHS = {"/", "/health", "/api/auth/login", "/api/auth/logout", "/api/auth/me"}


def _auth_enabled() -> bool:
    return os.getenv("DOCTOR_DEV_AUTH_REQUIRED", "0").lower() in {"1", "true", "yes", "on"}


def _admin_username() -> str:
    return os.getenv("DOCTOR_DEV_ADMIN_USERNAME", "admin")


def _admin_password() -> str:
    return os.getenv("DOCTOR_DEV_ADMIN_PASSWORD", "admin")


def _session_ttl_seconds() -> int:
    try:
        return max(300, int(os.getenv("DOCTOR_DEV_SESSION_TTL_SECONDS", str(12 * 60 * 60))))
    except ValueError:
        return 12 * 60 * 60


def _cookie_secure() -> bool:
    if os.getenv("DOCTOR_DEV_COOKIE_SECURE"):
        return os.getenv("DOCTOR_DEV_COOKIE_SECURE", "0").lower() in {"1", "true", "yes", "on"}
    return os.getenv("DOCTOR_DEV_PANEL_PUBLIC_URL", "").lower().startswith("https://")


def _app_secret() -> bytes:
    secret = os.getenv("DOCTOR_DEV_APP_SECRET") or os.getenv("DOCTOR_DEV_ADMIN_PASSWORD") or "doctor-dev-development-secret"
    return secret.encode("utf-8")


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _make_session(username: str) -> str:
    payload = {"sub": username, "iat": int(time.time()), "exp": int(time.time()) + _session_ttl_seconds(), "nonce": secrets.token_urlsafe(18)}
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_app_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _verify_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(_app_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64_decode(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        if not secrets.compare_digest(str(payload.get("sub", "")), _admin_username()):
            return None
        return str(payload.get("sub"))
    except Exception:
        return None


def _check_password(username: str, password: str) -> bool:
    return secrets.compare_digest(username, _admin_username()) and secrets.compare_digest(password, _admin_password())


def _basic_auth_ok(header: str | None) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        user, password = raw.split(":", 1)
    except Exception:
        return False
    return _check_password(user, password)


def _request_user(request: Request) -> str | None:
    if not _auth_enabled():
        return _admin_username()
    if _basic_auth_ok(request.headers.get("authorization")):
        return _admin_username()
    return _verify_session(request.cookies.get(SESSION_COOKIE))


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if _auth_enabled() and path not in AUTH_PUBLIC_PATHS and not path.startswith("/docs") and not path.startswith("/openapi"):
        if not _request_user(request):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "login required"}, status_code=401)
            return JSONResponse({"detail": "login required"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
async def startup() -> None:
    ensure_dirs()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(FRONTEND_HTML)


@app.get("/api/auth/me")
async def auth_me(request: Request) -> dict[str, Any]:
    user = _request_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return {"ok": True, "user_name": user, "auth_required": _auth_enabled()}


@app.post("/api/auth/login")
async def auth_login(body: dict[str, Any]) -> JSONResponse:
    username = str(body.get("username") or body.get("user_name") or "")
    password = str(body.get("password") or "")
    if not _check_password(username, password):
        raise HTTPException(status_code=401, detail="invalid username or password")
    response = JSONResponse({"ok": True, "user_name": username})
    response.set_cookie(
        SESSION_COOKIE,
        _make_session(username),
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=_session_ttl_seconds(),
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def auth_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "doctor_dev_panel", "version": "1.0.0"}


# -------------------------
# Remote discovery/resolution
# -------------------------

def _listener_to_remote_endpoint(node: NodeOut, core: CoreOut, inbound: InboundConfig, listener: InboundListener) -> dict[str, Any] | None:
    if not listener.enabled or listener.port_mode != "fixed" or listener.listen_port is None:
        return None
    host = listener.public_host or listener.listen_ip or node.address
    # 0.0.0.0 is a bind address, not a connect address. Use the node address for real remotes.
    if host in {"0.0.0.0", "::", ""}:
        host = node.address
    return {
        "host": host,
        "port": listener.listen_port,
        "node_id": node.id,
        "node_name": node.name,
        "core_id": core.id,
        "core_name": core.name,
        "inbound_id": inbound.id,
        "inbound_name": inbound.name,
        "listener_id": listener.id,
        "source": "remote_group",
        "tls_enabled": bool(inbound.tls.enabled),
        "tls_mode": inbound.tls.mode,
    }


def resolve_remote_target(target: RouteTarget) -> list[dict[str, Any]]:
    if target.type != TargetType.remote_group or not target.remote_node_id:
        return []
    node = store.get_node(target.remote_node_id)
    if not node:
        return []
    candidate_cores = store.list_cores(node.id)
    if target.remote_core_id:
        candidate_cores = [core for core in candidate_cores if core.id == target.remote_core_id or core.name == target.remote_core_id]

    endpoints: list[dict[str, Any]] = []
    for core in candidate_cores:
        for inbound in core.inbounds:
            if target.remote_inbound_id and inbound.id != target.remote_inbound_id and inbound.name != target.remote_inbound_id:
                continue
            if target.remote_group_id and target.remote_group_id not in {inbound.id, inbound.name, core.id, core.name}:
                continue
            for listener in inbound.listeners:
                endpoint = _listener_to_remote_endpoint(node, core, inbound, listener)
                if endpoint:
                    endpoints.append(endpoint)
    return endpoints


def build_config_for_apply(core: CoreOut):
    return build_generated_config(core, remote_resolver=resolve_remote_target)


def dry_run_for_panel(core: CoreOut) -> dict[str, Any]:
    return dry_run_summary(core, remote_resolver=resolve_remote_target)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def build_config_diff(left: dict[str, Any], right: dict[str, Any], left_label: str = "before", right_label: str = "after") -> dict[str, Any]:
    left_text = _json_text(left).splitlines()
    right_text = _json_text(right).splitlines()
    unified = list(difflib.unified_diff(left_text, right_text, fromfile=left_label, tofile=right_label, lineterm=""))
    added = sum(1 for line in unified if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in unified if line.startswith("-") and not line.startswith("---"))
    return {"ok": True, "added_lines": added, "removed_lines": removed, "diff": unified}


def _version_public(item: dict[str, Any], include_payload: bool = False) -> dict[str, Any]:
    public = {
        "id": item.get("id"),
        "version_no": item.get("version_no"),
        "created_at": item.get("created_at"),
        "kind": item.get("kind"),
        "status": item.get("status"),
        "node_id": item.get("node_id"),
        "core_id": item.get("core_id"),
        "core_name": item.get("core_name"),
        "saved_path": item.get("saved_path"),
        "summary": item.get("summary", {}),
    }
    if include_payload:
        public["core_snapshot"] = item.get("core_snapshot")
        public["generated_config"] = item.get("generated_config")
    return public


# -------------------------
# Certificate/TLS manager
# -------------------------


def _safe_domain_path(domain: str) -> str:
    cleaned = "".join(ch for ch in domain.lower().strip() if ch.isalnum() or ch in {"-", "."}).strip(".")
    if not cleaned:
        raise HTTPException(status_code=400, detail="invalid domain")
    return cleaned


def _certificate_to_ref(cert_id: str) -> CertificateRef:
    cert = store.get_certificate(cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="certificate not found")
    return CertificateRef(
        id=cert.id,
        name=cert.name,
        enabled=True,
        mode=cert.mode,
        domain=cert.domain,
        fullchain_path=cert.fullchain_path,
        privkey_path=cert.privkey_path,
        fullchain_content=cert.fullchain_content,
        privkey_content=cert.privkey_content,
    )


@app.get("/api/certificates")
async def list_certificates() -> list[dict[str, Any]]:
    return [cert.model_dump(exclude={"fullchain_content", "privkey_content"}) for cert in store.list_certificates()]


@app.get("/api/certificates/{cert_id}")
async def get_certificate(cert_id: str) -> dict[str, Any]:
    cert = store.get_certificate(cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="certificate not found")
    return cert.model_dump()


@app.post("/api/certificates")
async def create_certificate(body: CertificateCreate) -> dict[str, Any]:
    try:
        cert = store.create_certificate(body)
        validation = validate_certificate_ref(_certificate_to_ref(cert.id), panel_can_read_paths=True)
        data = cert.model_dump(exclude={"fullchain_content", "privkey_content"})
        data["validation"] = validation.model_dump()
        return data
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/certificates/upload")
async def upload_certificate(
    name: str = Form(...),
    domain: str = Form(...),
    fullchain: UploadFile = File(...),
    privkey: UploadFile = File(...),
) -> dict[str, Any]:
    safe_domain = _safe_domain_path(domain)
    cert_dir = CERT_DIR / safe_domain
    cert_dir.mkdir(parents=True, exist_ok=True)
    fullchain_path = cert_dir / "fullchain.pem"
    privkey_path = cert_dir / "privkey.pem"
    fullchain_bytes = await fullchain.read()
    privkey_bytes = await privkey.read()
    if len(fullchain_bytes) > 1024 * 1024 or len(privkey_bytes) > 1024 * 1024:
        raise HTTPException(status_code=400, detail="certificate files are too large for panel upload")
    fullchain_path.write_bytes(fullchain_bytes)
    privkey_path.write_bytes(privkey_bytes)
    body = CertificateCreate(
        name=name,
        domain=safe_domain,
        mode=CertificateMode.uploaded_from_host,
        fullchain_path=str(fullchain_path),
        privkey_path=str(privkey_path),
        location="panel",
    )
    try:
        cert = store.create_certificate(body)
        validation = validate_certificate_ref(_certificate_to_ref(cert.id), panel_can_read_paths=True)
        data = cert.model_dump(exclude={"fullchain_content", "privkey_content"})
        data["validation"] = validation.model_dump()
        return data
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/certificates/validate")
async def validate_certificate(body: CertificateValidationRequest) -> dict[str, Any]:
    try:
        ref = certificate_ref_from_request(body)
        return validate_certificate_ref(ref, panel_can_read_paths=True).model_dump()
    except ValueError as exc:
        return {"ok": False, "mode": body.mode, "domain": body.domain, "message": str(exc), "warnings": [], "details": {}}


@app.delete("/api/certificates/{cert_id}")
async def delete_certificate(cert_id: str) -> dict[str, Any]:
    if not store.delete_certificate(cert_id):
        raise HTTPException(status_code=404, detail="certificate not found")
    return {"ok": True, "message": "certificate deleted", "certificate_id": cert_id}


@app.get("/api/certificates/{cert_id}/ref")
async def get_certificate_ref(cert_id: str) -> dict[str, Any]:
    return _certificate_to_ref(cert_id).model_dump()


@app.get("/api/nodes")
async def list_nodes() -> list[dict[str, Any]]:
    return [node.model_dump() for node in store.list_nodes()]


@app.post("/api/nodes")
async def create_node(body: NodeCreate) -> dict[str, Any]:
    try:
        node = store.create_node(body)
        store.create_audit_log("node_created", "node", node.id, f"Node created: {node.name}", {"node_name": node.name})
        return node.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/nodes/{node_id}")
async def update_node(node_id: str, body: NodeCreate) -> dict[str, Any]:
    try:
        before = store.get_node(node_id)
        node = store.update_node(node_id, body)
        store.create_audit_log("node_updated", "node", node.id, f"Node updated: {node.name}", {"before_name": before.name if before else None, "node_name": node.name})
        return node.model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="node not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/nodes/{node_id}")
async def delete_node(node_id: str) -> dict[str, Any]:
    node = store.get_node(node_id)
    if not store.delete_node(node_id):
        raise HTTPException(status_code=404, detail="node not found")
    store.create_audit_log("node_deleted", "node", node_id, f"Node deleted: {node.name if node else node_id}", {"node_id": node_id})
    return {"ok": True, "message": "node deleted", "node_id": node_id}


@app.post("/api/nodes/bulk-delete")
async def bulk_delete_nodes(body: dict[str, list[str]]) -> dict[str, Any]:
    node_ids = body.get("node_ids", [])
    if not node_ids:
        raise HTTPException(status_code=400, detail="node_ids is required")
    result = store.delete_nodes(node_ids)
    store.create_audit_log("nodes_bulk_deleted", "node", None, f"Bulk node delete: {len(result['deleted'])} deleted", result)
    return {"ok": True, **result}


@app.get("/api/nodes/{node_id}")
async def get_node(node_id: str) -> dict[str, Any]:
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump()


@app.get("/api/nodes/{node_id}/discovery")
async def node_discovery(node_id: str) -> dict[str, Any]:
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    cores = store.list_cores(node_id)
    items = []
    for core in cores:
        core_item = {"id": core.id, "name": core.name, "status": core.status, "inbounds": []}
        for inbound in core.inbounds:
            listeners = []
            for listener in inbound.listeners:
                endpoint = _listener_to_remote_endpoint(node, core, inbound, listener)
                listeners.append({"listener": listener.model_dump(), "runtime_endpoint": endpoint})
            core_item["inbounds"].append({"id": inbound.id, "name": inbound.name, "enabled": inbound.enabled, "listeners": listeners})
        items.append(core_item)
    return {"ok": True, "node": node.model_dump(), "cores": items}


@app.post("/api/nodes/{node_id}/check-status")
async def check_node(node_id: str) -> dict[str, Any]:
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        status = await check_agent_status(node)
        updated = store.update_node_status(node_id, "online")
        return {"ok": True, "node": updated.model_dump(), "agent": status}
    except Exception as exc:  # noqa: BLE001
        store.update_node_status(node_id, "offline")
        return {"ok": False, "node_id": node_id, "status": "offline", "error": str(exc)}


@app.get("/api/nodes/{node_id}/runtime")
async def node_runtime(node_id: str) -> dict[str, Any]:
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        return await fetch_runtime(node)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"failed to fetch node runtime: {exc}") from exc


@app.post("/api/nodes/{node_id}/stop-runtime")
async def node_stop_runtime(node_id: str) -> dict[str, Any]:
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        return await stop_runtime(node)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"failed to stop node runtime: {exc}") from exc


@app.get("/api/nodes/{node_id}/logs")
async def node_logs(node_id: str, limit: int = Query(200, ge=1, le=2000)) -> dict[str, Any]:
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        return await fetch_logs(node, limit=limit)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"failed to fetch node logs: {exc}") from exc


@app.get("/api/cores")
async def list_cores(node_id: str | None = None) -> list[dict[str, Any]]:
    return [core.model_dump() for core in store.list_cores(node_id=node_id)]


@app.post("/api/cores")
async def create_core(body: CoreCreate) -> dict[str, Any]:
    try:
        core = store.create_core(body)
        store.create_audit_log("core_created", "core", core.id, f"Core created: {core.name}", {"core_id": core.id, "node_id": core.node_id})
        return core.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@app.put("/api/cores/{core_id}")
async def update_core(core_id: str, body: CoreCreate) -> dict[str, Any]:
    try:
        before = store.get_core(core_id)
        updated = store.update_core(core_id, body)
        store.create_audit_log("core_updated", "core", core_id, f"Core updated: {updated.name}", {"core_id": core_id, "before_status": before.status if before else None})
        return updated.model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="core not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/cores/{core_id}")
async def delete_core(core_id: str) -> dict[str, Any]:
    core = store.get_core(core_id)
    if not store.delete_core(core_id):
        raise HTTPException(status_code=404, detail="core not found")
    store.create_audit_log("core_deleted", "core", core_id, f"Core deleted: {core.name if core else core_id}", {"core_id": core_id})
    return {"ok": True, "message": "core deleted", "core_id": core_id}


@app.get("/api/cores/{core_id}")
async def get_core(core_id: str) -> dict[str, Any]:
    core = store.get_core(core_id)
    if not core:
        raise HTTPException(status_code=404, detail="core not found")
    return core.model_dump()


@app.get("/api/cores/{core_id}/config")
async def get_generated_config(core_id: str) -> dict[str, Any]:
    core = store.get_core(core_id)
    if not core:
        raise HTTPException(status_code=404, detail="core not found")
    return build_config_for_apply(core).model_dump()


@app.post("/api/cores/{core_id}/dry-run")
async def dry_run_core(core_id: str) -> dict[str, Any]:
    core = store.get_core(core_id)
    if not core:
        raise HTTPException(status_code=404, detail="core not found")
    summary = dry_run_for_panel(core)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / f"{core.name}.{core.id}.dry-run.json"
    path.write_text(json.dumps(summary["generated_config"], ensure_ascii=False, indent=2), encoding="utf-8")
    summary["saved_preview_path"] = str(path)
    version = store.create_config_version(core=core, generated_config=summary["generated_config"], kind="dry_run", status="preview", summary={"warnings": summary.get("warnings", []), "changes": summary.get("changes", [])}, saved_path=str(path))
    summary["version"] = _version_public(version)
    return summary


@app.post("/api/cores/{core_id}/apply")
async def apply_core(core_id: str) -> dict[str, Any]:
    core = store.get_core(core_id)
    if not core:
        raise HTTPException(status_code=404, detail="core not found")
    node = store.get_node(core.node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    config = build_config_for_apply(core)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / f"{core.name}.{core.id}.applied.json"
    path.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    version = store.create_config_version(core=core, generated_config=config.model_dump(), kind="apply", status="pending", summary={"target_node": node.name}, saved_path=str(path))
    try:
        result = await apply_config(node, config)
        core.status = "runtime_running" if result.ok else "apply_failed"
        store.upsert_core(core)
        final_status = "applied" if result.ok else "apply_failed"
        store.update_config_version_status(version["id"], final_status, {"agent_message": result.message})
        store.create_audit_log("core_applied", "core", core.id, f"Core applied: {core.name} as v{version['version_no']}", {"core_id": core.id, "version_id": version["id"], "version_no": version["version_no"]})
        data = result.model_dump()
        data["panel_saved_config"] = str(path)
        data["version"] = _version_public(store.get_config_version(version["id"]) or version)
        data["resolved_remote_endpoints"] = sum(len(t.get("resolved_endpoints", []) or []) for r in config.routes for t in r.get("targets", []))
        return data
    except httpx.HTTPError as exc:
        core.status = "apply_failed"
        store.upsert_core(core)
        store.update_config_version_status(version["id"], "apply_failed", {"error": str(exc)})
        store.create_audit_log("core_apply_failed", "core", core.id, f"Core apply failed: {core.name}", {"core_id": core.id, "version_id": version["id"], "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"failed to apply config to agent: {exc}") from exc


@app.get("/api/cores/{core_id}/versions")
async def list_core_versions(core_id: str, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    if not store.get_core(core_id):
        raise HTTPException(status_code=404, detail="core not found")
    return {"ok": True, "core_id": core_id, "versions": [_version_public(item) for item in store.list_config_versions(core_id=core_id, limit=limit)]}


@app.get("/api/config-versions/{version_id}")
async def get_config_version(version_id: str) -> dict[str, Any]:
    version = store.get_config_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="config version not found")
    return {"ok": True, "version": _version_public(version, include_payload=True)}


@app.get("/api/cores/{core_id}/diff")
async def diff_core_versions(core_id: str, from_version_id: str | None = None, to_version_id: str | None = None) -> dict[str, Any]:
    core = store.get_core(core_id)
    if not core:
        raise HTTPException(status_code=404, detail="core not found")
    versions = store.list_config_versions(core_id=core_id, limit=500)
    if from_version_id:
        left_version = store.get_config_version(from_version_id)
    else:
        left_version = versions[1] if len(versions) > 1 else None
    if to_version_id:
        right_version = store.get_config_version(to_version_id)
        right_payload = right_version.get("generated_config") if right_version else None
        right_label = f"v{right_version.get('version_no')}" if right_version else "missing"
    else:
        right_payload = build_config_for_apply(core).model_dump()
        right_label = "current_draft"
    left_payload = left_version.get("generated_config") if left_version else {}
    left_label = f"v{left_version.get('version_no')}" if left_version else "empty"
    diff = build_config_diff(left_payload, right_payload or {}, left_label=left_label, right_label=right_label)
    diff.update({"core_id": core_id, "from_version": _version_public(left_version) if left_version else None, "to_version": _version_public(right_version) if to_version_id and right_version else None, "to_label": right_label})
    return diff


@app.post("/api/cores/{core_id}/rollback/{version_id}")
async def rollback_core(core_id: str, version_id: str, apply_after_restore: bool = Query(True)) -> dict[str, Any]:
    current = store.get_core(core_id)
    if not current:
        raise HTTPException(status_code=404, detail="core not found")
    version = store.get_config_version(version_id)
    if not version or version.get("core_id") != core_id:
        raise HTTPException(status_code=404, detail="config version not found for this core")
    restored = CoreOut.model_validate(version["core_snapshot"])
    restored.status = "rollback_restored"
    store.upsert_core(restored)
    store.create_audit_log("core_rollback_restored", "core", core_id, f"Core restored from v{version.get('version_no')}: {restored.name}", {"core_id": core_id, "version_id": version_id, "version_no": version.get("version_no"), "apply_after_restore": apply_after_restore})
    response: dict[str, Any] = {"ok": True, "message": "core restored from saved version", "restored_core": restored.model_dump(), "restored_from": _version_public(version)}
    if apply_after_restore:
        response["apply_result"] = await apply_core(core_id)
    return response


@app.get("/api/audit-logs")
async def audit_logs(limit: int = Query(200, ge=1, le=1000), entity_id: str | None = None) -> dict[str, Any]:
    return {"ok": True, "logs": store.list_audit_logs(limit=limit, entity_id=entity_id)}


@app.post("/api/test/tcp")
async def test_tcp(host: str = "127.0.0.1", port: int = 18090, payload: str = "hello-from-panel") -> dict[str, Any]:
    try:
        return tcp_roundtrip(host=host, port=port, payload=payload)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "host": host, "port": port, "error": str(exc)}


@app.post("/api/test/tls-tcp")
async def test_tls_tcp(host: str = "127.0.0.1", port: int = 18443, payload: str = "hello-from-panel-tls", verify: bool = False) -> dict[str, Any]:
    try:
        return tls_roundtrip(host=host, port=port, payload=payload, verify=verify)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "mode": "tls", "host": host, "port": port, "error": str(exc)}

