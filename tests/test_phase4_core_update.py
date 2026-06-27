from uuid import uuid4

from fastapi.testclient import TestClient

from doctor_dev_panel.app import app


def test_phase4_create_update_delete_core_from_builder_shape():
    client = TestClient(app)
    client.post("/api/dev/seed-local")
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]
    suffix = uuid4().hex[:8]

    internal_route_id = f"route_internal_{suffix}"
    internal_inbound_id = f"inbound_internal_{suffix}"
    public_route_id = f"route_public_{suffix}"

    payload = {
        "node_id": node_id,
        "name": f"phase4-builder-core-{suffix}",
        "enabled": True,
        "description": "created from phase4 builder shaped API test",
        "inbounds": [
            {
                "id": f"inbound_public_{suffix}",
                "name": "public-entry-inbound",
                "type": "tunnel",
                "protocol": "tcp",
                "enabled": True,
                "listeners": [{"listen_ip": "127.0.0.1", "listen_port": 18080, "port_mode": "fixed", "enabled": True}],
                "tls": {"enabled": False, "mode": "none"},
                "limits": {"max_users": 20, "max_active_connections": 5},
                "route_id": public_route_id,
            },
            {
                "id": internal_inbound_id,
                "name": "internal-hop-inbound",
                "type": "tunnel",
                "protocol": "tcp",
                "enabled": True,
                "listeners": [{"listen_ip": "127.0.0.1", "listen_port": 18100, "port_mode": "fixed", "enabled": True}],
                "tls": {"enabled": False, "mode": "none"},
                "limits": {"max_users": 100, "max_active_connections": 50},
                "route_id": internal_route_id,
            },
        ],
        "routes": [
            {
                "id": public_route_id,
                "name": "public-route",
                "balancer": "failover",
                "fallback_behavior": "error",
                "enabled": True,
                "targets": [{"type": "local_inbound", "enabled": True, "priority": 10, "weight": 1, "local_inbound_id": internal_inbound_id}],
            },
            {
                "id": internal_route_id,
                "name": "internal-to-final-targets",
                "balancer": "weighted_round_robin",
                "fallback_behavior": "error",
                "enabled": True,
                "targets": [{"type": "static", "enabled": True, "priority": 10, "weight": 1, "host": "127.0.0.1", "ports": [3000, 3001]}],
            },
        ],
        "advanced_config": {"created_by": "phase4_visual_builder"},
    }

    created = client.post("/api/cores", json=payload)
    assert created.status_code == 200
    core_id = created.json()["id"]

    payload["name"] = f"phase4-builder-core-updated-{suffix}"
    updated = client.put(f"/api/cores/{core_id}", json=payload)
    assert updated.status_code == 200
    assert updated.json()["name"].endswith(suffix)
    assert updated.json()["status"] == "draft_updated"

    dry_run = client.post(f"/api/cores/{core_id}/dry-run")
    assert dry_run.status_code == 200
    assert dry_run.json()["generated_config"]["version"] == "doctor-dev.phase7.v1"

    deleted = client.delete(f"/api/cores/{core_id}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
