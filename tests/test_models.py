from doctor_dev_shared.models import CoreCreate, InboundConfig, InboundListener, RouteConfig, RouteTarget


def test_core_supports_multiple_listeners_and_static_ports():
    route = RouteConfig(name="route-a", targets=[RouteTarget(type="static", host="127.0.0.1", ports=[3000, 3001])])
    inbound = InboundConfig(name="inbound-a", listeners=[InboundListener(listen_ip="127.0.0.1", listen_port=18080), InboundListener(listen_ip="127.0.0.1", listen_port=18081)], route_id=route.id)
    core = CoreCreate(node_id="node_1", name="core-a", inbounds=[inbound], routes=[route])
    assert len(core.inbounds[0].listeners) == 2
    assert core.routes[0].targets[0].ports == [3000, 3001]
