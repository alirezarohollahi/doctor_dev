from doctor_dev_agent.tunnel_engine import TunnelManager
from doctor_dev_shared.config_builder import build_generated_config
from doctor_dev_shared.models import CoreOut, InboundConfig, InboundListener, RouteConfig, RouteTarget, TargetType


def test_config_builder_resolves_remote_group_endpoint():
    endpoint = {"host": "127.0.0.1", "port": 19100, "node_name": "local-node-b"}
    route = RouteConfig(name="route-remote", targets=[RouteTarget(type=TargetType.remote_group, remote_node_id="node_b")])
    inbound = InboundConfig(name="entry", listeners=[InboundListener(listen_port=18090)], route_id=route.id)
    core = CoreOut(node_id="node_a", name="entry-core", inbounds=[inbound], routes=[route])
    config = build_generated_config(core, remote_resolver=lambda target: [endpoint])
    target = config.routes[0]["targets"][0]
    assert target["type"] == "remote_group"
    assert target["resolved_endpoints"] == [endpoint]


def test_tunnel_manager_turns_remote_group_resolved_endpoints_into_runtime_targets():
    manager = TunnelManager(lambda level, message: None)
    route = {
        "id": "route_remote",
        "name": "remote",
        "balancer": "failover",
        "targets": [
            {
                "id": "target_remote",
                "type": "remote_group",
                "enabled": True,
                "priority": 10,
                "weight": 1,
                "remote_node_id": "node_b",
                "resolved_endpoints": [{"host": "127.0.0.1", "port": 19100}],
            }
        ],
    }
    resolved, warnings = manager._resolve_route_targets(route, {})
    assert warnings == []
    assert len(resolved) == 1
    assert resolved[0].source_type == "remote_group"
    assert resolved[0].host == "127.0.0.1"
    assert resolved[0].port == 19100
