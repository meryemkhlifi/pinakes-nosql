from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

# Endpoints that are still stubs. Remove a line here when its task is done.
STILL_STUBS = ["/popular", "/monitoring/alerts"]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_stubs_return_501():
    for url in STILL_STUBS:
        assert client.get(url).status_code == 501, url


def test_openapi_lists_every_endpoint():
    paths = client.get("/openapi.json").json()["paths"]
    expected = [
        "/health",
        "/catalog/genres",
        "/catalog/genres/{genre}/authors",
        "/catalog/works/{work_id}",
        "/search",
        "/suggest",
        "/popular",
        "/graph/path",
        "/graph/neighbors/{author_id}",
        "/graph/influence/top",
        "/events/read",
        "/events/work/{work_id}",
        "/events/user/{user_id}",
        "/monitoring/alerts",
    ]
    for p in expected:
        assert p in paths, p
