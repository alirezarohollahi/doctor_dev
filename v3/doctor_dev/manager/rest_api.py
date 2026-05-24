from __future__ import annotations

from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from doctor_dev.manager.core import DoctorManager
from doctor_dev.models.config import GroupConfig


def create_app(manager: DoctorManager) -> FastAPI:
    app = FastAPI(title="doctor_dev manager", version="0.1.0")

    async def require_token(authorization: Optional[str] = Header(default=None)) -> None:
        token = manager.config.manager.api_token
        if not token:
            return
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid or missing token")

    @app.on_event("startup")
    async def startup() -> None:
        await manager.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await manager.stop()

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "manager": manager.config.manager.name}

    @app.get("/status", dependencies=[Depends(require_token)])
    async def status() -> dict:
        return manager.status()

    @app.get("/config", dependencies=[Depends(require_token)])
    async def config() -> dict:
        return manager.config_dump()

    @app.get("/groups", dependencies=[Depends(require_token)])
    async def groups() -> List[dict]:
        return manager.groups_status()

    @app.post("/groups", dependencies=[Depends(require_token)])
    async def create_or_replace_group(group_config: GroupConfig) -> dict:
        return await manager.upsert_group_config(group_config)

    @app.get("/groups/{group_name}", dependencies=[Depends(require_token)])
    async def group_status(group_name: str) -> dict:
        result = manager.group_status(group_name)
        if result is None:
            raise HTTPException(status_code=404, detail="group not found")
        return result

    @app.get("/groups/{group_name}/inbounds", dependencies=[Depends(require_token)])
    async def group_inbounds(group_name: str) -> dict:
        result = manager.group_inbounds(group_name)
        if result is None:
            raise HTTPException(status_code=404, detail="group not found")
        return result

    @app.post("/reload", dependencies=[Depends(require_token)])
    async def reload_config() -> dict:
        await manager.reload_config()
        return {"status": "ok", "message": "config reloaded"}

    @app.post("/sync", dependencies=[Depends(require_token)])
    async def sync_now() -> dict:
        await manager.sync_now()
        return {"status": "ok", "message": "remote dependencies synced"}

    @app.put("/groups/{group_name}", dependencies=[Depends(require_token)])
    async def replace_group(group_name: str, group_config: GroupConfig) -> dict:
        if group_config.name != group_name:
            raise HTTPException(status_code=400, detail="path group name and body group name must match")
        return await manager.upsert_group_config(group_config)

    @app.delete("/groups/{group_name}", dependencies=[Depends(require_token)])
    async def delete_group(group_name: str) -> dict:
        ok = await manager.delete_group_config(group_name)
        if not ok:
            raise HTTPException(status_code=404, detail="group not found")
        return {"status": "ok", "message": f"group {group_name} deleted"}

    @app.post("/groups/{group_name}/restart", dependencies=[Depends(require_token)])
    async def restart_group(group_name: str) -> dict:
        ok = await manager.restart_group(group_name)
        if not ok:
            raise HTTPException(status_code=404, detail="group not found")
        return {"status": "ok", "message": f"group {group_name} restarted"}

    @app.middleware("http")
    async def add_manager_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Doctor-Dev-Manager"] = manager.config.manager.name
        return response

    return app
