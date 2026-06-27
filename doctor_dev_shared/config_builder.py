from __future__ import annotations

from typing import Any, Callable

from .certificates import validate_certificate_ref
from .models import CoreOut, GeneratedConfig, RouteTarget, TargetType

RemoteResolver = Callable[[RouteTarget], list[dict[str, Any]]]


def target_to_runtime(target: RouteTarget, remote_resolver: RemoteResolver | None = None) -> dict[str, Any]:
    base = {"id": target.id, "type": target.type, "enabled": target.enabled, "priority": target.priority, "weight": target.weight}
    if target.type == TargetType.static:
        base.update({"host": target.host, "ports": target.ports})
    elif target.type == TargetType.remote_group:
        base.update({
            "remote_node_id": target.remote_node_id,
            "remote_core_id": target.remote_core_id,
            "remote_group_id": target.remote_group_id,
            "remote_inbound_id": target.remote_inbound_id,
            "resolved_endpoints": remote_resolver(target) if remote_resolver else [],
        })
    elif target.type == TargetType.local_inbound:
        base.update({"local_inbound_id": target.local_inbound_id})
    return base


def build_generated_config(core: CoreOut, remote_resolver: RemoteResolver | None = None) -> GeneratedConfig:
    inbounds = []
    for inbound in core.inbounds:
        inbounds.append({
            "id": inbound.id,
            "name": inbound.name,
            "type": inbound.type,
            "protocol": inbound.protocol,
            "enabled": inbound.enabled,
            "listeners": [listener.model_dump() for listener in inbound.listeners],
            "tls": inbound.tls.model_dump(),
            "limits": inbound.limits.model_dump(),
            "route_id": inbound.route_id,
        })
    routes = []
    for route in core.routes:
        routes.append({
            "id": route.id,
            "name": route.name,
            "balancer": route.balancer,
            "fallback_behavior": route.fallback_behavior,
            "enabled": route.enabled,
            "targets": [target_to_runtime(target, remote_resolver=remote_resolver) for target in route.targets],
        })
    return GeneratedConfig(version="doctor-dev.v1", node_id=core.node_id, core_id=core.id, core_name=core.name, enabled=core.enabled, inbounds=inbounds, routes=routes, advanced_config=core.advanced_config)


def dry_run_summary(core: CoreOut, remote_resolver: RemoteResolver | None = None) -> dict[str, Any]:
    config = build_generated_config(core, remote_resolver=remote_resolver)
    listeners_count = sum(len(inbound.listeners) for inbound in core.inbounds)
    targets_count = sum(len(route.targets) for route in core.routes)
    remote_targets_count = sum(1 for route in core.routes for target in route.targets if target.type == TargetType.remote_group)
    resolved_remote_endpoints = 0
    for route in config.routes:
        for target in route.get("targets", []):
            resolved_remote_endpoints += len(target.get("resolved_endpoints", []) or [])
    warnings: list[str] = []
    for inbound in core.inbounds:
        if inbound.limits.max_users is None:
            warnings.append(f"Inbound {inbound.name}: max_users is not set")
        if inbound.limits.max_active_connections is None:
            warnings.append(f"Inbound {inbound.name}: max_active_connections is not set")
        if inbound.tls.enabled:
            cert_result = validate_certificate_ref(inbound.tls, panel_can_read_paths=True)
            if not cert_result.ok:
                warnings.append(f"Inbound {inbound.name}: TLS validation failed: {cert_result.message}")
            for cert_warning in cert_result.warnings:
                warnings.append(f"Inbound {inbound.name}: TLS warning: {cert_warning}")
    if remote_targets_count and resolved_remote_endpoints == 0:
        warnings.append("Remote-group target exists, but no runtime endpoint was resolved. Check remote node/core/inbound/listeners.")
    return {
        "ok": True,
        "version": "1.0.0",
        "core_id": core.id,
        "core_name": core.name,
        "node_id": core.node_id,
        "changes": [
            f"Create/update core: {core.name}",
            f"Configure {len(core.inbounds)} inbound(s)",
            f"Configure {listeners_count} listener(s)",
            f"Configure {len(core.routes)} route(s)",
            f"Configure {targets_count} route target(s)",
            f"Resolve {remote_targets_count} remote-group target(s) to {resolved_remote_endpoints} endpoint(s)",
        ],
        "warnings": warnings,
        "generated_config": config.model_dump(),
    }
