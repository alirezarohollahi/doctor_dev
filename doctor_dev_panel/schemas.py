from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class NodeBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=255)
    node_port: int = Field(default=62050, ge=1, le=65535)
    api_port: int = Field(default=62051, ge=1, le=65535)
    api_key: str = Field(min_length=1, max_length=255)
    certificate: str = Field(default="", max_length=20000)
    enabled: bool = True

    # Node installer/runtime settings. The panel stores them now and uses api_port
    # for management; node_port is reserved for data-plane/listener traffic.
    usage_ratio: float = Field(default=1, ge=0)
    connection_type: str = Field(default="grpc", pattern="^grpc$")
    keep_alive_value: int = Field(default=60, ge=1)
    keep_alive_unit: str = Field(default="seconds", pattern="^(seconds|minutes|hours)$")
    data_limit_gb: float | None = Field(default=None, ge=0)
    default_timeout: int = Field(default=10, ge=1)
    internal_timeout: int = Field(default=15, ge=1)
    proxy_url: str = Field(default="", max_length=500)

    @field_validator("connection_type", mode="before")
    @classmethod
    def normalize_connection_type(cls, value: object) -> str:
        # The current node agent supports gRPC control-plane communication only.
        # Older UI builds used values like direct/proxy; normalize them so edits
        # of old records do not fail with a raw Pydantic pattern error.
        value_text = str(value or "grpc").strip().lower()
        return "grpc" if value_text in {"", "grpc", "direct", "proxy", "rest"} else value_text


class CoreInboundBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    bind_ip: str = Field(default="0.0.0.0", max_length=120)
    public_host: str = Field(default="", max_length=255)
    port_mode: Literal["fixed", "random"] = "fixed"
    fixed_ports: list[int] = Field(default_factory=list)
    random_count: int = Field(default=1, ge=1, le=4096)
    target_type: Literal["static", "balancer"] = "static"
    target_host: str = Field(default="127.0.0.1", max_length=255)
    target_port: int = Field(default=80, ge=1, le=65535)
    target_balancer: str = Field(default="", max_length=120)
    certificate: str = Field(default="", max_length=20000)
    enabled: bool = True
    notes: str = Field(default="", max_length=500)

    @field_validator("fixed_ports")
    @classmethod
    def valid_ports(cls, value: list[int]) -> list[int]:
        unique: list[int] = []
        for port in value:
            if not 1 <= int(port) <= 65535:
                raise ValueError("fixed_ports must contain ports between 1 and 65535")
            if int(port) not in unique:
                unique.append(int(port))
        return unique


class CoreBalancerEndpointBody(BaseModel):
    type: Literal["static", "node_inbound"] = "static"
    host: str = Field(default="127.0.0.1", max_length=255)
    port: int = Field(default=80, ge=1, le=65535)
    node_id: str = Field(default="", max_length=120)
    core_id: str = Field(default="", max_length=120)
    inbound_name: str = Field(default="", max_length=120)
    weight: float = Field(default=1, ge=0)
    certificate: str = Field(default="", max_length=20000)
    enabled: bool = True
    notes: str = Field(default="", max_length=500)

    @field_validator("port", mode="before")
    @classmethod
    def normalize_endpoint_port(cls, value: object) -> int:
        # The UI hides port for Node Inbound endpoints, but Pydantic still
        # receives the field. Empty strings must not produce a raw validation
        # error like "unable to parse string as an integer". Runtime/panel
        # enrichment resolves the real selected inbound port before apply.
        if value in {None, ""}:
            return 80
        try:
            port = int(value)
        except (TypeError, ValueError):
            return 80
        return port if 1 <= port <= 65535 else 80


class CoreBalancerBody(BaseModel):
    alias: str = Field(min_length=1, max_length=120)
    strategy: Literal["round_robin", "random", "failover", "least_connections"] = "round_robin"
    endpoints: list[CoreBalancerEndpointBody] = Field(default_factory=list)
    enabled: bool = True
    notes: str = Field(default="", max_length=500)


class CoreDependencyBody(BaseModel):
    type: Literal["core", "node"] = "core"
    ref_id: str = Field(default="", max_length=120)
    required: bool = True
    notes: str = Field(default="", max_length=500)


class CoreAdvancedConfigBody(BaseModel):
    enabled: bool = False
    json_config: str = Field(default="", max_length=200000)


class AdvancedConfigValidateBody(BaseModel):
    json_config: str = Field(default="", max_length=200000)


class CoreBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    node_id: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    inbounds: list[CoreInboundBody] = Field(default_factory=list)
    balancers: list[CoreBalancerBody] = Field(default_factory=list)
    dependencies: list[CoreDependencyBody] = Field(default_factory=list)
    advanced_config: CoreAdvancedConfigBody = Field(default_factory=CoreAdvancedConfigBody)
