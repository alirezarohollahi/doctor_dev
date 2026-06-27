from fastapi.testclient import TestClient

from doctor_dev_panel.app import app


def test_login_page_auth_flow(monkeypatch):
    monkeypatch.setenv("DOCTOR_DEV_AUTH_REQUIRED", "1")
    monkeypatch.setenv("DOCTOR_DEV_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("DOCTOR_DEV_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setenv("DOCTOR_DEV_APP_SECRET", "test-secret")
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "id=\"loginScreen\"" in page.text
    assert "id=\"loginForm\"" in page.text

    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/nodes").status_code == 401

    bad = client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"username": "admin", "password": "secret-pass"})
    assert ok.status_code == 200
    assert "doctor_dev_panel_session" in ok.headers.get("set-cookie", "")
    assert client.get("/api/auth/me").json()["user_name"] == "admin"
    assert client.get("/api/nodes").status_code == 200

    client.post("/api/auth/logout")
    assert client.get("/api/nodes").status_code == 401


def test_basic_auth_still_works_for_cli(monkeypatch):
    import base64
    monkeypatch.setenv("DOCTOR_DEV_AUTH_REQUIRED", "1")
    monkeypatch.setenv("DOCTOR_DEV_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("DOCTOR_DEV_ADMIN_PASSWORD", "secret-pass")
    token = base64.b64encode(b"admin:secret-pass").decode()
    client = TestClient(app)
    res = client.get("/api/nodes", headers={"Authorization": f"Basic {token}"})
    assert res.status_code == 200
