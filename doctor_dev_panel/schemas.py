from __future__ import annotations

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class NodeBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=255)
    node_port: int = Field(default=62050, ge=1, le=65535)
    api_key: str = Field(min_length=1, max_length=255)
    certificate: str = Field(default="", max_length=20000)
    enabled: bool = False

    # Reserved for upcoming runtime/config phases. The panel stores them now,
    # but no runtime forwarding logic is attached in this foundation step.
    usage_ratio: float = Field(default=1, ge=0)
    api_port: int = Field(default=62051, ge=1, le=65535)
    connection_type: str = Field(default="grpc", pattern="^(grpc|rest)$")
    keep_alive_value: int = Field(default=60, ge=1)
    keep_alive_unit: str = Field(default="seconds", pattern="^(seconds|minutes|hours)$")
    data_limit_gb: float | None = Field(default=None, ge=0)
    default_timeout: int = Field(default=10, ge=1)
    internal_timeout: int = Field(default=15, ge=1)
    proxy_url: str = Field(default="", max_length=500)
