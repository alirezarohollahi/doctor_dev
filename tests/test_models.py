from doctor_dev_shared.models import NodeCreate, NodeAdvancedSettings, CoreCreate, InboundConfig, InboundListener, RouteConfig, RouteTarget


def test_node_model_accepts_production_settings():
    node = NodeCreate(name="edge-node-1", address="203.0.113.10", node_port=62050, api_key="secret", advanced=NodeAdvancedSettings(api_port=9101))
    assert node.name == "edge-node-1"
    assert node.advanced.api_port == 9101


def test_core_model_accepts_multiple_listeners_and_targets():
    route = RouteConfig(name="edge-route", balancer="round_robin", targets=[RouteTarget(type="static", host="127.0.0.1", ports=[3000, 3001])])
    inbound = InboundConfig(name="public-entry", listeners=[InboundListener(listen_ip="0.0.0.0", listen_port=443), InboundListener(listen_ip="0.0.0.0", listen_port=8443)], route_id=route.id)
    core = CoreCreate(node_id="node_1", name="edge-core", inbounds=[inbound], routes=[route])
    assert len(core.inbounds[0].listeners) == 2
    assert core.routes[0].targets[0].ports == [3000, 3001]
