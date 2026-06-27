from fastapi.testclient import TestClient
from doctor_dev_panel.app import app


def test_panel_health():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["service"] == "doctor_dev_panel"
    assert res.json()["version"] == "1.0.0"


def test_seed_local_nodes():
    client = TestClient(app)
    res = client.post("/api/test-lab/seed-local")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["total_nodes"] >= 2


def test_create_remote_route_sample():
    client = TestClient(app)
    client.post("/api/test-lab/seed-local")
    res = client.post("/api/test-lab/create-remote-route")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["test"]["port"] == 18090
    assert len(data["apply_order"]) == 2
