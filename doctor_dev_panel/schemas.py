from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class NodeBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=255)
    api_port: int = Field(default=62051, ge=1, le=65535)
    api_key: str = Field(min_length=1, max_length=255)
    update_interval: int = Field(default=10, ge=1, le=86400)
    peer_token_refresh_interval: int = Field(default=30, ge=5, le=86400)
    peer_token_ttl: int = Field(default=120, ge=10, le=86400)
    certificate: str = Field(default="", max_length=20000)
    enabled: bool = True


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

    @field_validator("target_port", mode="before")
    @classmethod
    def normalize_target_port(cls, value: object) -> int:
        # The routing UI can temporarily keep this field empty while a user is
        # switching target modes. Keep validation user-friendly and let topology
        # checks decide whether the final static forwarding target is valid.
        if value in {None, ""}:
            return 80
        try:
            port = int(value)
        except (TypeError, ValueError):
            return 80
        return port if 1 <= port <= 65535 else 80

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




