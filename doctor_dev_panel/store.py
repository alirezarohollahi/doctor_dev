from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from doctor_dev_shared.models import CertificateCreate, CertificateOut, CoreCreate, CoreOut, NodeCreate, NodeOut, new_id
from .settings import STATE_FILE, ensure_dirs


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JsonStore:
    def __init__(self, path: Path = STATE_FILE):
        ensure_dirs()
        self.path = path
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(self._empty_state())

    def _empty_state(self) -> dict[str, Any]:
        return {"nodes": [], "cores": [], "certificates": [], "config_versions": [], "audit_logs": []}

    def _read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return self._empty_state()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Backward-compatible state upgrade for older state files.
            changed = False
            for key, default in self._empty_state().items():
                if key not in data:
                    data[key] = default
                    changed = True
            if changed:
                self._write(data)
            return data

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)


    def list_certificates(self) -> list[CertificateOut]:
        return [CertificateOut.model_validate(item) for item in self._read().get("certificates", [])]

    def get_certificate(self, cert_id: str) -> CertificateOut | None:
        return next((cert for cert in self.list_certificates() if cert.id == cert_id), None)

    def create_certificate(self, body: CertificateCreate) -> CertificateOut:
        if any(cert.name == body.name for cert in self.list_certificates()):
            raise ValueError(f"certificate name already exists: {body.name}")
        now = now_iso()
        cert = CertificateOut.model_validate({**body.model_dump(), "created_at": now, "updated_at": now})
        data = self._read()
        data.setdefault("certificates", []).append(cert.model_dump())
        self._write(data)
        return cert

    def delete_certificate(self, cert_id: str) -> bool:
        data = self._read()
        certs = data.setdefault("certificates", [])
        next_certs = [item for item in certs if item.get("id") != cert_id]
        if len(next_certs) == len(certs):
            return False
        data["certificates"] = next_certs
        self._write(data)
        return True

    def list_nodes(self) -> list[NodeOut]:
        return [NodeOut.model_validate(item) for item in self._read().get("nodes", [])]

    def get_node(self, node_id: str) -> NodeOut | None:
        return next((node for node in self.list_nodes() if node.id == node_id), None)

    def upsert_node(self, node: NodeOut) -> NodeOut:
        data = self._read()
        nodes = data.setdefault("nodes", [])
        for index, item in enumerate(nodes):
            if item["id"] == node.id:
                nodes[index] = node.model_dump()
                self._write(data)
                return node
        nodes.append(node.model_dump())
        self._write(data)
        return node

    def create_node(self, body: NodeCreate) -> NodeOut:
        if any(node.name == body.name for node in self.list_nodes()):
            raise ValueError(f"node name already exists: {body.name}")
        return self.upsert_node(NodeOut.model_validate(body.model_dump()))

    def update_node(self, node_id: str, body: NodeCreate) -> NodeOut:
        existing = self.get_node(node_id)
        if not existing:
            raise KeyError(node_id)
        for node in self.list_nodes():
            if node.id != node_id and node.name == body.name:
                raise ValueError(f"node name already exists: {body.name}")
        updated = NodeOut.model_validate({**body.model_dump(), "id": node_id, "status": existing.status, "last_seen_at": existing.last_seen_at})
        return self.upsert_node(updated)

    def delete_node(self, node_id: str) -> bool:
        data = self._read()
        nodes = data.setdefault("nodes", [])
        if not any(item.get("id") == node_id for item in nodes):
            return False
        data["nodes"] = [item for item in nodes if item.get("id") != node_id]
        removed_core_ids = {item.get("id") for item in data.setdefault("cores", []) if item.get("node_id") == node_id}
        data["cores"] = [item for item in data.setdefault("cores", []) if item.get("node_id") != node_id]
        if removed_core_ids:
            data["config_versions"] = [item for item in data.setdefault("config_versions", []) if item.get("core_id") not in removed_core_ids]
        self._write(data)
        return True

    def delete_nodes(self, node_ids: list[str]) -> dict[str, Any]:
        requested = list(dict.fromkeys(node_ids))
        deleted = []
        missing = []
        for node_id in requested:
            if self.delete_node(node_id):
                deleted.append(node_id)
            else:
                missing.append(node_id)
        return {"deleted": deleted, "missing": missing, "requested": requested}

    def update_node_status(self, node_id: str, status: str) -> NodeOut:
        node = self.get_node(node_id)
        if not node:
            raise KeyError(node_id)
        node.status = status
        if status == "online":
            node.last_seen_at = now_iso()
        return self.upsert_node(node)

    def list_cores(self, node_id: str | None = None) -> list[CoreOut]:
        cores = [CoreOut.model_validate(item) for item in self._read().get("cores", [])]
        return [core for core in cores if core.node_id == node_id] if node_id else cores

    def get_core(self, core_id: str) -> CoreOut | None:
        return next((core for core in self.list_cores() if core.id == core_id), None)

    def create_core(self, body: CoreCreate) -> CoreOut:
        if not self.get_node(body.node_id):
            raise ValueError(f"node does not exist: {body.node_id}")
        if any(core.name == body.name for core in self.list_cores(body.node_id)):
            raise ValueError(f"core name already exists on node: {body.name}")
        core = CoreOut.model_validate(body.model_dump())
        data = self._read()
        data.setdefault("cores", []).append(core.model_dump())
        self._write(data)
        return core

    def update_core(self, core_id: str, body: CoreCreate) -> CoreOut:
        existing = self.get_core(core_id)
        if not existing:
            raise KeyError(core_id)
        if not self.get_node(body.node_id):
            raise ValueError(f"node does not exist: {body.node_id}")
        for core in self.list_cores(body.node_id):
            if core.id != core_id and core.name == body.name:
                raise ValueError(f"core name already exists on node: {body.name}")
        updated = CoreOut.model_validate({**body.model_dump(), "id": core_id, "status": "draft_updated"})
        return self.upsert_core(updated)

    def delete_core(self, core_id: str) -> bool:
        data = self._read()
        cores = data.setdefault("cores", [])
        next_cores = [item for item in cores if item.get("id") != core_id]
        if len(next_cores) == len(cores):
            return False
        data["cores"] = next_cores
        self._write(data)
        return True

    def upsert_core(self, core: CoreOut) -> CoreOut:
        data = self._read()
        cores = data.setdefault("cores", [])
        for index, item in enumerate(cores):
            if item["id"] == core.id:
                cores[index] = core.model_dump()
                self._write(data)
                return core
        cores.append(core.model_dump())
        self._write(data)
        return core


    # -------------------------
    # Config versions + audit logs
    # -------------------------

    def create_audit_log(self, action: str, entity_type: str, entity_id: str | None = None, message: str | None = None, details: dict[str, Any] | None = None, actor: str = "panel-admin") -> dict[str, Any]:
        item = {
            "id": new_id("audit"),
            "created_at": now_iso(),
            "actor": actor,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "message": message or action,
            "details": details or {},
        }
        data = self._read()
        data.setdefault("audit_logs", []).append(item)
        self._write(data)
        return item

    def list_audit_logs(self, limit: int = 200, entity_id: str | None = None) -> list[dict[str, Any]]:
        items = self._read().get("audit_logs", [])
        if entity_id:
            items = [item for item in items if item.get("entity_id") == entity_id or item.get("details", {}).get("core_id") == entity_id]
        return list(reversed(items))[:limit]

    def create_config_version(
        self,
        *,
        core: CoreOut,
        generated_config: dict[str, Any],
        kind: str,
        status: str = "created",
        summary: dict[str, Any] | None = None,
        saved_path: str | None = None,
    ) -> dict[str, Any]:
        data = self._read()
        existing = [v for v in data.setdefault("config_versions", []) if v.get("core_id") == core.id]
        version_no = max([int(v.get("version_no", 0)) for v in existing] or [0]) + 1
        item = {
            "id": new_id("ver"),
            "version_no": version_no,
            "created_at": now_iso(),
            "kind": kind,
            "status": status,
            "node_id": core.node_id,
            "core_id": core.id,
            "core_name": core.name,
            "core_snapshot": core.model_dump(),
            "generated_config": generated_config,
            "summary": summary or {},
            "saved_path": saved_path,
        }
        data["config_versions"].append(item)
        self._write(data)
        self.create_audit_log(
            action=f"config_{kind}",
            entity_type="core",
            entity_id=core.id,
            message=f"Config version v{version_no} created for core {core.name}",
            details={"version_id": item["id"], "version_no": version_no, "status": status, "core_id": core.id},
        )
        return item

    def list_config_versions(self, core_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        items = self._read().get("config_versions", [])
        if core_id:
            items = [item for item in items if item.get("core_id") == core_id]
        items = sorted(items, key=lambda item: item.get("version_no", 0), reverse=True)
        return items[:limit]

    def get_config_version(self, version_id: str) -> dict[str, Any] | None:
        return next((item for item in self._read().get("config_versions", []) if item.get("id") == version_id), None)

    def update_config_version_status(self, version_id: str, status: str, details: dict[str, Any] | None = None) -> dict[str, Any] | None:
        data = self._read()
        for item in data.setdefault("config_versions", []):
            if item.get("id") == version_id:
                item["status"] = status
                if details:
                    item.setdefault("summary", {}).setdefault("status_details", {}).update(details)
                self._write(data)
                return item
        return None


store = JsonStore()
