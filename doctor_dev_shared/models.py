from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class KeepAliveUnit(str, Enum):
    seconds = "seconds"
    minutes = "minutes"
    hours = "hours"


class ConnectionType(str, Enum):
    grpc = "grpc"
    http = "http"


class TargetType(str, Enum):
    static = "static"
    remote_group = "remote_group"
    local_inbound = "local_inbound"


class BalancerType(str, Enum):
    round_robin = "round_robin"
    random = "random"
    failover = "failover"
    weighted_round_robin = "weighted_round_robin"


class PortMode(str, Enum):
    fixed = "fixed"
    random = "random"
    range = "range"


class CertificateMode(str, Enum):
    none = "none"
    file_on_node = "file_on_node"
    file_on_panel = "file_on_panel"
    pasted_content = "pasted_content"
    uploaded_from_host = "uploaded_from_host"


class DoctorBaseModel(BaseModel):
    model_config = {"use_enum_values": True, "extra": "forbid", "str_strip_whitespace": True}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class KeepAliveSettings(DoctorBaseModel):
    value: int = Field(default=60, ge=1)
    unit: KeepAliveUnit = KeepAliveUnit.seconds


class CertificateRef(DoctorBaseModel):
    id: str | None = None
    name: str | None = None
    enabled: bool = False
    mode: CertificateMode = CertificateMode.none
    domain: str | None = None
    fullchain_path: str | None = None
    privkey_path: str | None = None
    fullchain_content: str | None = None
    privkey_content: str | None = None

    @model_validator(mode="after")
    def validate_certificate(self) -> "CertificateRef":
        if not self.enabled:
            return self
        if self.mode == CertificateMode.none:
            raise ValueError("certificate mode is required when TLS is enabled")
        if self.mode in {CertificateMode.file_on_node, CertificateMode.file_on_panel, CertificateMode.uploaded_from_host}:
            if not self.fullchain_path or not self.privkey_path:
                raise ValueError("fullchain_path and privkey_path are required for file certificate modes")
        if self.mode == CertificateMode.pasted_content:
            if not self.fullchain_content or not self.privkey_content:
                raise ValueError("fullchain_content and privkey_content are required for pasted_content mode")
        return self


class CertificateCreate(DoctorBaseModel):
    name: str = Field(min_length=2, max_length=80)
    domain: str = Field(min_length=1, max_length=255)
    mode: CertificateMode
    fullchain_path: str | None = None
    privkey_path: str | None = None
    fullchain_content: str | None = None
    privkey_content: str | None = None
    location: Literal["panel", "node", "inline"] = "panel"

    @model_validator(mode="after")
    def validate_input(self) -> "CertificateCreate":
        ref = CertificateRef(
            enabled=True,
            mode=self.mode,
            domain=self.domain,
            fullchain_path=self.fullchain_path,
            privkey_path=self.privkey_path,
            fullchain_content=self.fullchain_content,
            privkey_content=self.privkey_content,
        )
        _ = ref
        return self


class CertificateOut(CertificateCreate):
    id: str = Field(default_factory=lambda: new_id("cert"))
    status: str = "stored"
    created_at: str | None = None
    updated_at: str | None = None


class CertificateValidationRequest(DoctorBaseModel):
    mode: CertificateMode
    domain: str | None = None
    fullchain_path: str | None = None
    privkey_path: str | None = None
    fullchain_content: str | None = None
    privkey_content: str | None = None


class CertificateValidationResult(DoctorBaseModel):
    ok: bool
    mode: str
    domain: str | None = None
    message: str
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class NodeAdvancedSettings(DoctorBaseModel):
    api_port: int = Field(default=62051, ge=1, le=65535)
    keep_alive: KeepAliveSettings = Field(default_factory=KeepAliveSettings)
    data_limit_gb: int | None = Field(default=None, ge=1)
    default_timeout: int = Field(default=10, ge=1)
    internal_timeout: int = Field(default=15, ge=1)
    proxy_url: str | None = None


class NodeCreate(DoctorBaseModel):
    name: str = Field(min_length=2, max_length=80)
    address: str = Field(min_length=1, max_length=255)
    node_port: int = Field(default=62050, ge=1, le=65535)
    api_key: str = Field(min_length=1, max_length=255)
    connection_type: ConnectionType = ConnectionType.grpc
    advanced: NodeAdvancedSettings = Field(default_factory=NodeAdvancedSettings)
    certificate: str | None = None


class NodeOut(NodeCreate):
    id: str = Field(default_factory=lambda: new_id("node"))
    status: str = "unknown"
    last_seen_at: str | None = None


class InboundListener(DoctorBaseModel):
    id: str = Field(default_factory=lambda: new_id("listener"))
    listen_ip: str = "0.0.0.0"
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    port_mode: PortMode = PortMode.fixed
    port_range_start: int | None = Field(default=None, ge=1, le=65535)
    port_range_end: int | None = Field(default=None, ge=1, le=65535)
    public_host: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_ports(self) -> "InboundListener":
        if self.port_mode == PortMode.fixed and self.listen_port is None:
            raise ValueError("listen_port is required when port_mode=fixed")
        if self.port_mode == PortMode.range:
            if self.port_range_start is None or self.port_range_end is None:
                raise ValueError("port_range_start and port_range_end are required when port_mode=range")
            if self.port_range_start > self.port_range_end:
                raise ValueError("port_range_start must be <= port_range_end")
        return self


class InboundLimits(DoctorBaseModel):
    max_users: int | None = Field(default=None, ge=1)
    max_active_connections: int | None = Field(default=None, ge=1)


class RouteTarget(DoctorBaseModel):
    id: str = Field(default_factory=lambda: new_id("target"))
    type: TargetType
    enabled: bool = True
    priority: int = Field(default=100, ge=0)
    weight: int = Field(default=1, ge=1)
    host: str | None = None
    ports: list[int] = Field(default_factory=list)
    remote_node_id: str | None = None
    remote_core_id: str | None = None
    remote_group_id: str | None = None
    remote_inbound_id: str | None = None
    local_inbound_id: str | None = None

    @field_validator("ports")
    @classmethod
    def validate_port_values(cls, ports: list[int]) -> list[int]:
        for port in ports:
            if port < 1 or port > 65535:
                raise ValueError("ports must be between 1 and 65535")
        return ports

    @model_validator(mode="after")
    def validate_target(self) -> "RouteTarget":
        if self.type == TargetType.static and (not self.host or not self.ports):
            raise ValueError("static target requires host and at least one port")
        if self.type == TargetType.remote_group and not self.remote_node_id:
            raise ValueError("remote_group target requires remote_node_id")
        if self.type == TargetType.local_inbound and not self.local_inbound_id:
            raise ValueError("local_inbound target requires local_inbound_id")
        return self


class RouteConfig(DoctorBaseModel):
    id: str = Field(default_factory=lambda: new_id("route"))
    name: str = Field(min_length=2, max_length=80)
    balancer: BalancerType = BalancerType.round_robin
    fallback_behavior: Literal["error", "next", "drop"] = "error"
    targets: list[RouteTarget] = Field(default_factory=list)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_route(self) -> "RouteConfig":
        if self.enabled and not [target for target in self.targets if target.enabled]:
            raise ValueError("enabled route must have at least one enabled target")
        return self


class InboundConfig(DoctorBaseModel):
    id: str = Field(default_factory=lambda: new_id("inbound"))
    name: str = Field(min_length=2, max_length=80)
    type: Literal["tunnel"] = "tunnel"
    protocol: str = "tcp"
    enabled: bool = True
    listeners: list[InboundListener] = Field(default_factory=list)
    tls: CertificateRef = Field(default_factory=CertificateRef)
    limits: InboundLimits = Field(default_factory=InboundLimits)
    route_id: str | None = None

    @model_validator(mode="after")
    def validate_inbound(self) -> "InboundConfig":
        if self.enabled and not [listener for listener in self.listeners if listener.enabled]:
            raise ValueError("enabled inbound must have at least one enabled listener")
        return self


class CoreCreate(DoctorBaseModel):
    node_id: str
    name: str = Field(min_length=2, max_length=80)
    enabled: bool = True
    description: str | None = None
    inbounds: list[InboundConfig] = Field(default_factory=list)
    routes: list[RouteConfig] = Field(default_factory=list)
    advanced_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_core_graph(self) -> "CoreCreate":
        inbound_ids = {inbound.id for inbound in self.inbounds}
        route_ids = {route.id for route in self.routes}
        inbound_names = [inbound.name for inbound in self.inbounds]
        route_names = [route.name for route in self.routes]
        if len(inbound_names) != len(set(inbound_names)):
            raise ValueError("inbound names must be unique inside a core")
        if len(route_names) != len(set(route_names)):
            raise ValueError("route names must be unique inside a core")
        for inbound in self.inbounds:
            if inbound.route_id and inbound.route_id not in route_ids:
                raise ValueError(f"inbound {inbound.name} references missing route_id={inbound.route_id}")
        for route in self.routes:
            for target in route.targets:
                if target.type == TargetType.local_inbound and target.local_inbound_id not in inbound_ids:
                    raise ValueError(f"route {route.name} references missing local_inbound_id={target.local_inbound_id}")
        return self


class CoreOut(CoreCreate):
    id: str = Field(default_factory=lambda: new_id("core"))
    status: str = "draft"


class GeneratedConfig(DoctorBaseModel):
    version: str = "doctor-dev.v1"
    node_id: str
    core_id: str
    core_name: str
    enabled: bool
    inbounds: list[dict[str, Any]]
    routes: list[dict[str, Any]]
    advanced_config: dict[str, Any] = Field(default_factory=dict)


class ApplyResult(DoctorBaseModel):
    ok: bool
    message: str
    node_id: str | None = None
    core_id: str | None = None
    saved_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
