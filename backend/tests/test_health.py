from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "llm_enabled" in body


def test_root() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "refer-backend"
