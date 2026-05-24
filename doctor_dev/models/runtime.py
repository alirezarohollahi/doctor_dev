from __future__ import annotations

from pydantic import BaseModel, Field


class ProcessRuntime(BaseModel):
    process_id: str
    group_name: str
    listen_host: str
    public_host: str
    listen_port: int
    status: str = "stopped"
    active_connections: int = 0
    connection_count: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    last_error: str | None = None


class GroupRuntime(BaseModel):
    name: str
    status: str = "stopped"
    processes: list[ProcessRuntime] = Field(default_factory=list)


class RemoteDependencyRuntime(BaseModel):
    name: str
    manager_url: str
    group_name: str
    status: str = "unknown"
    last_error: str | None = None
    last_sync_at: str | None = None
    inbounds: list[dict] = Field(default_factory=list)


class RuntimeState(BaseModel):
    groups: dict[str, GroupRuntime] = Field(default_factory=dict)
    remote_dependencies: dict[str, RemoteDependencyRuntime] = Field(default_factory=dict)
