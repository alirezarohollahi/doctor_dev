from doctor_dev_shared.config_builder import build_generated_config
from doctor_dev_shared.models import CoreOut, InboundConfig, InboundListener, NodeCreate, RouteConfig, RouteTarget


def test_generated_config_contains_balancer_and_policies():
    route = RouteConfig(name="route", balancer="weighted_round_robin", targets=[RouteTarget(type="static", host="127.0.0.1", ports=[3000], weight=2)])
    inbound = InboundConfig(name="in", listeners=[InboundListener(listen_ip="0.0.0.0", listen_port=443)], route_id=route.id, limits={"max_users": 10, "max_active_connections": 20})
    core = CoreOut(node_id="node", name="core", inbounds=[inbound], routes=[route])
    generated = build_generated_config(core)
    assert generated.routes[0]["balancer"] == "weighted_round_robin"
    assert generated.inbounds[0]["limits"]["max_active_connections"] == 20
