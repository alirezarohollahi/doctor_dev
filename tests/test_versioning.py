from fastapi.testclient import TestClient

from doctor_dev_panel.app import app


def _sample_core_payload(node_id: str, name: str = "versioned-versioning-core") -> dict:
    route_id = "route_versioning"
    inbound_id = "inbound_versioning"
    return {
        "node_id": node_id,
        "name": name,
        "enabled": True,
        "description": "versioned versioning test core",
        "inbounds": [
            {
                "id": inbound_id,
                "name": "versioned-entry",
                "type": "tunnel",
                "protocol": "tcp",
                "enabled": True,
                "listeners": [
                    {"id": "listener_versioning", "listen_ip": "127.0.0.1", "listen_port": 18280, "port_mode": "fixed", "enabled": True}
                ],
                "tls": {"enabled": False, "mode": "none"},
                "limits": {"max_users": 10, "max_active_connections": 5},
                "route_id": route_id,
            }
        ],
        "routes": [
            {
                "id": route_id,
                "name": "versioned-to-echo",
                "balancer": "round_robin",
                "fallback_behavior": "error",
                "enabled": True,
                "targets": [
                    {"id": "target_versioning", "type": "static", "enabled": True, "host": "127.0.0.1", "ports": [3000], "priority": 10, "weight": 1}
                ],
            }
        ],
        "advanced_config": {"created_by": "versioned_test"},
    }


def test_versioned_dry_run_creates_version_and_diff_and_audit():
    client = TestClient(app)
    client.post("/api/test-lab/seed-local")
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]

    create = client.post("/api/cores", json=_sample_core_payload(node_id))
    assert create.status_code == 200, create.text
    core_id = create.json()["id"]

    dry_run_1 = client.post(f"/api/cores/{core_id}/dry-run")
    assert dry_run_1.status_code == 200, dry_run_1.text
    version_1 = dry_run_1.json()["version"]
    assert version_1["version_no"] == 1
    assert version_1["kind"] == "dry_run"

    payload = _sample_core_payload(node_id)
    payload["routes"][0]["targets"][0]["ports"] = [3001]
    update = client.put(f"/api/cores/{core_id}", json=payload)
    assert update.status_code == 200, update.text

    dry_run_2 = client.post(f"/api/cores/{core_id}/dry-run")
    assert dry_run_2.status_code == 200, dry_run_2.text
    version_2 = dry_run_2.json()["version"]
    assert version_2["version_no"] == 2

    versions = client.get(f"/api/cores/{core_id}/versions").json()["versions"]
    assert [v["version_no"] for v in versions[:2]] == [2, 1]

    diff = client.get(f"/api/cores/{core_id}/diff", params={"from_version_id": version_1["id"], "to_version_id": version_2["id"]})
    assert diff.status_code == 200, diff.text
    diff_text = "\n".join(diff.json()["diff"])
    assert "3000" in diff_text and "3001" in diff_text

    audit = client.get("/api/audit-logs", params={"entity_id": core_id}).json()["logs"]
    actions = {row["action"] for row in audit}
    assert "core_created" in actions
    assert "config_dry_run" in actions


def test_versioned_rollback_restores_core_without_apply():
    client = TestClient(app)
    client.post("/api/test-lab/seed-local")
    node_id = client.get("/api/nodes").json()[0]["id"]
    create = client.post("/api/cores", json=_sample_core_payload(node_id, name="versioned-rollback-core"))
    assert create.status_code == 200, create.text
    core_id = create.json()["id"]

    v1 = client.post(f"/api/cores/{core_id}/dry-run").json()["version"]
    payload = _sample_core_payload(node_id, name="versioned-rollback-core")
    payload["description"] = "changed description"
    payload["routes"][0]["targets"][0]["ports"] = [3002]
    assert client.put(f"/api/cores/{core_id}", json=payload).status_code == 200

    rollback = client.post(f"/api/cores/{core_id}/rollback/{v1['id']}", params={"apply_after_restore": "false"})
    assert rollback.status_code == 200, rollback.text
    restored = client.get(f"/api/cores/{core_id}").json()
    assert restored["description"] == "versioned versioning test core"
    assert restored["routes"][0]["targets"][0]["ports"] == [3000]
