# tests
from fastapi.testclient import TestClient

from rentgraph.main import app


def test_healthz() -> None:
    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_openapi_exposed() -> None:
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
        assert "/api/v1/contracts" in spec["paths"]
