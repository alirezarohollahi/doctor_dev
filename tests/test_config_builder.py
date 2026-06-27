from doctor_dev_shared.config_builder import build_generated_config
from doctor_dev_shared.models import CoreOut, InboundConfig, InboundListener, RouteConfig, RouteTarget


def test_config_builder_outputs_routes_and_inbounds():
    route = RouteConfig(name="route-a", targets=[RouteTarget(type="static", host="127.0.0.1", ports=[8080])])
    inbound = InboundConfig(name="inbound-a", listeners=[InboundListener(listen_port=18080)], route_id=route.id)
    core = CoreOut(node_id="node_1", name="core-a", inbounds=[inbound], routes=[route])
    config = build_generated_config(core)
    assert config.core_name == "core-a"
    assert config.inbounds[0]["route_id"] == route.id
    assert config.routes[0]["targets"][0]["ports"] == [8080]
