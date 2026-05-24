from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class TargetStrategy(str, Enum):
    round_robin = "round_robin"
    failover = "failover"


class StaticTarget(BaseModel):
    type: Literal["static"] = "static"
    host: str
    port: int

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value


class RemoteGroupTarget(BaseModel):
    type: Literal["remote_group"] = "remote_group"
    dependency: str


Target = Union[StaticTarget, RemoteGroupTarget]


class GroupConfig(BaseModel):
    name: str
    process_count: int = Field(ge=1, le=4096)
    listen_host: str = "0.0.0.0"
    public_host: Optional[str] = None
    port_mode: Literal["random", "fixed"] = "random"
    fixed_ports: List[int] = Field(default_factory=list)
    targets: List[Target] = Field(default_factory=list)
    strategy: TargetStrategy = TargetStrategy.round_robin
    enabled: bool = True

    @field_validator("fixed_ports")
    @classmethod
    def valid_fixed_ports(cls, value: List[int]) -> List[int]:
        for port in value:
            if not 1 <= port <= 65535:
                raise ValueError("fixed_ports must contain ports between 1 and 65535")
        return value


class RemoteDependencyConfig(BaseModel):
    name: str
    manager_url: str
    group_name: str
    token: Optional[str] = None
    sync_interval_seconds: int = Field(default=10, ge=2)


class ManagerConfig(BaseModel):
    name: str
    host: str = "0.0.0.0"
    port: int = 7000
    public_host: Optional[str] = None
    api_token: Optional[str] = None
    log_file: str = "doctor_dev.log"

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value


class DoctorConfig(BaseModel):
    manager: ManagerConfig
    groups: List[GroupConfig] = Field(default_factory=list)
    remote_dependencies: List[RemoteDependencyConfig] = Field(default_factory=list)

    def group_by_name(self, name: str) -> Optional[GroupConfig]:
        for group in self.groups:
            if group.name == name:
                return group
        return None

    def dependency_by_name(self, name: str) -> Optional[RemoteDependencyConfig]:
        for dep in self.remote_dependencies:
            if dep.name == name:
                return dep
        return None
