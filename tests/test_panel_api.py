from fastapi.testclient import TestClient

from doctor_dev_panel.app import app


def test_health_endpoint():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["service"] == "doctor_dev_panel"
