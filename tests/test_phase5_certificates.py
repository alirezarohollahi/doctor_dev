from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from doctor_dev_panel.app import app


def test_phase7_certificate_validation_from_paths():
    client = TestClient(app)
    suffix = uuid4().hex[:8]
    fullchain = str(Path("certs/local.test/fullchain.pem"))
    privkey = str(Path("certs/local.test/privkey.pem"))

    validation = client.post(
        "/api/certificates/validate",
        json={"mode": "file_on_panel", "domain": "local.test", "fullchain_path": fullchain, "privkey_path": privkey},
    )
    assert validation.status_code == 200
    assert validation.json()["ok"] is True

    created = client.post(
        "/api/certificates",
        json={
            "name": f"local-test-cert-{suffix}",
            "domain": "local.test",
            "mode": "file_on_panel",
            "fullchain_path": fullchain,
            "privkey_path": privkey,
            "location": "panel",
        },
    )
    assert created.status_code == 200
    cert = created.json()
    assert cert["validation"]["ok"] is True
    assert cert["mode"] == "file_on_panel"

    cert_ref = client.get(f"/api/certificates/{cert['id']}/ref")
    assert cert_ref.status_code == 200
    assert cert_ref.json()["enabled"] is True
    assert cert_ref.json()["mode"] == "file_on_panel"


def test_phase7_core_dry_run_includes_tls_ref():
    client = TestClient(app)
    client.post("/api/dev/seed-local")
    nodes = client.get("/api/nodes").json()
    node_id = nodes[0]["id"]
    suffix = uuid4().hex[:8]
    route_id = f"route_tls_{suffix}"

    payload = {
        "node_id": node_id,
        "name": f"phase7-tls-core-{suffix}",
        "enabled": True,
        "description": "phase7 TLS dry-run test",
        "inbounds": [
            {
                "id": f"inbound_tls_{suffix}",
                "name": "tls-entry-inbound",
                "type": "tunnel",
                "protocol": "tcp",
                "enabled": True,
                "listeners": [{"listen_ip": "127.0.0.1", "listen_port": 18443, "port_mode": "fixed", "enabled": True}],
                "tls": {
                    "enabled": True,
                    "mode": "file_on_panel",
                    "domain": "local.test",
                    "fullchain_path": "certs/local.test/fullchain.pem",
                    "privkey_path": "certs/local.test/privkey.pem",
                },
                "limits": {"max_users": 20, "max_active_connections": 5},
                "route_id": route_id,
            }
        ],
        "routes": [
            {
                "id": route_id,
                "name": "tls-route",
                "balancer": "round_robin",
                "fallback_behavior": "error",
                "enabled": True,
                "targets": [{"type": "static", "enabled": True, "priority": 10, "weight": 1, "host": "127.0.0.1", "ports": [3000]}],
            }
        ],
        "advanced_config": {"created_by": "phase7_tls_test"},
    }
    created = client.post("/api/cores", json=payload)
    assert created.status_code == 200
    dry_run = client.post(f"/api/cores/{created.json()['id']}/dry-run")
    assert dry_run.status_code == 200
    generated = dry_run.json()["generated_config"]
    assert generated["version"] == "doctor-dev.phase7.v1"
    assert generated["inbounds"][0]["tls"]["enabled"] is True
    assert generated["inbounds"][0]["tls"]["mode"] == "file_on_panel"
