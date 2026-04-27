"""Tests for /api/auth/register and /api/auth/login."""

import json


def test_register_and_login(client):
    # Register
    resp = client.post(
        "/api/auth/register",
        data=json.dumps({"username": "testuser", "password": "test1234", "nickname": "Tester"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 200
    assert body["data"]["username"] == "testuser"
    assert body["data"]["role"] == "USER"

    # Login
    resp = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "testuser", "password": "test1234"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 200
    assert "token" in body["data"]
    assert body["data"]["user"]["username"] == "testuser"


def test_register_duplicate(client):
    payload = json.dumps({"username": "dupuser", "password": "test1234"})
    client.post("/api/auth/register", data=payload, content_type="application/json")
    resp = client.post("/api/auth/register", data=payload, content_type="application/json")
    body = resp.get_json()
    assert body["code"] == 1000  # BUSINESS_ERROR
    assert "already exists" in body["message"]


def test_login_wrong_password(client):
    payload = json.dumps({"username": "wrongpw", "password": "test1234"})
    client.post("/api/auth/register", data=payload, content_type="application/json")
    resp = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "wrongpw", "password": "badpassword"}),
        content_type="application/json",
    )
    body = resp.get_json()
    assert body["code"] == 401


def test_login_validation_error(client):
    resp = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "ab", "password": "12345"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
