from __future__ import annotations

from typing import Dict, List, Optional

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
    last_error: Optional[str] = None


class GroupRuntime(BaseModel):
    name: str
    status: str = "stopped"
    processes: List[ProcessRuntime] = Field(default_factory=list)


class RemoteDependencyRuntime(BaseModel):
    name: str
    manager_url: str
    group_name: str
    status: str = "unknown"
    last_error: Optional[str] = None
    last_sync_at: Optional[str] = None
    inbounds: List[dict] = Field(default_factory=list)


class RuntimeState(BaseModel):
    groups: Dict[str, GroupRuntime] = Field(default_factory=dict)
    remote_dependencies: Dict[str, RemoteDependencyRuntime] = Field(default_factory=dict)
