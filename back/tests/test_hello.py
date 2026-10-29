"""Tests for GET /api/hello."""


def test_hello_returns_success(client):
    resp = client.get("/api/hello")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["code"] == 200
    assert data["data"] == "Hello from Flask!"


def test_versioned_hello_returns_success(client):
    resp = client.get("/api/v1/hello")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["code"] == 200
    assert data["data"] == "Hello from Flask!"
