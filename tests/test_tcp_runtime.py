from doctor_dev_agent.tunnel_engine import RouteRuntime, TargetEntry
from doctor_dev_shared.models import CoreCreate, InboundConfig, InboundListener, RouteConfig, RouteTarget, TargetType, BalancerType


def test_weighted_round_robin_sequence():
    route = {"id": "route_1", "name": "r", "balancer": "weighted_round_robin"}
    runtime = RouteRuntime(route, [TargetEntry(id="a", host="127.0.0.1", port=3000, weight=2), TargetEntry(id="b", host="127.0.0.1", port=3001, weight=1)])
    ports = [runtime.ordered_targets()[0].port for _ in range(6)]
    assert ports == [3000, 3000, 3001, 3000, 3000, 3001]


def test_local_inbound_target_is_valid_inside_same_core():
    internal_route = RouteConfig(name="internal", targets=[RouteTarget(type=TargetType.static, host="127.0.0.1", ports=[3000])])
    internal = InboundConfig(name="internal-inbound", listeners=[InboundListener(listen_ip="127.0.0.1", listen_port=18100)], route_id=internal_route.id)
    public_route = RouteConfig(name="public", balancer=BalancerType.failover, targets=[RouteTarget(type=TargetType.local_inbound, local_inbound_id=internal.id)])
    public = InboundConfig(name="public-inbound", listeners=[InboundListener(listen_ip="127.0.0.1", listen_port=18080)], route_id=public_route.id)
    core = CoreCreate(node_id="node_1", name="core", inbounds=[public, internal], routes=[public_route, internal_route])
    assert core.inbounds[0].route_id == public_route.id
    assert core.routes[0].targets[0].local_inbound_id == internal.id
