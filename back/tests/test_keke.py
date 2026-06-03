"""Tests for /api/keke/track and /api/keke/story/generate."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.extensions import db
from app.models import Device, Event
from app.services import story_service


def _post(client, url: str, payload: dict[str, Any]):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def test_track_visit_persists_event(client):
    resp = _post(
        client,
        "/api/keke/track",
        {
            "event": "visit",
            "device_id": "did-test-1",
            "from": "app",
            "ua": "iPhone",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["code"] == 200

    row = db.session.query(Event).filter_by(device_id="did-test-1").first()
    assert row is not None
    assert row.event_name == "visit"
    assert row.source == "app"
    assert row.ua == "iPhone"


def test_visit_registers_device_once(client):
    # First visit creates a `devices` row.
    _post(
        client,
        "/api/keke/track",
        {"event": "visit", "device_id": "did-once", "from": "app", "ua": "iPhone"},
    )
    rows = db.session.query(Device).filter_by(device_id="did-once").all()
    assert len(rows) == 1

    # Second visit (e.g. user cleared localStorage) does NOT duplicate.
    _post(
        client,
        "/api/keke/track",
        {"event": "visit", "device_id": "did-once", "from": "share", "ua": "Android"},
    )
    rows = db.session.query(Device).filter_by(device_id="did-once").all()
    assert len(rows) == 1
    # First-touch attribution stays — we do not overwrite source / ua.
    assert rows[0].source == "app"
    assert rows[0].ua == "iPhone"


def test_non_visit_event_does_not_register_device(client):
    _post(
        client,
        "/api/keke/track",
        {"event": "save_open", "device_id": "did-saveonly", "from": "app"},
    )
    rows = db.session.query(Device).filter_by(device_id="did-saveonly").all()
    assert rows == []


def test_track_invalid_event_returns_400(client):
    resp = _post(
        client,
        "/api/keke/track",
        {"event": "hack", "device_id": "did-test-2"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == 400


def test_track_missing_device_id_returns_400(client):
    resp = _post(client, "/api/keke/track", {"event": "visit"})
    assert resp.status_code == 400


def test_generate_story_missing_keyword_returns_400(client):
    resp = _post(
        client,
        "/api/keke/story/generate",
        {"device_id": "did-test-3", "from": "app", "keyword": ""},
    )
    assert resp.status_code == 400


def test_generate_story_without_key_returns_business_error(client):
    # TestConfig inherits BaseConfig where DEEPSEEK_API_KEY defaults to "".
    resp = _post(
        client,
        "/api/keke/story/generate",
        {"device_id": "did-test-4", "from": "app", "keyword": "下雨天"},
    )
    body = resp.get_json()
    assert body["code"] == 1000  # BUSINESS_ERROR
    assert "未配置" in body["message"]

    # The implicit generate_start should still have been written.
    row = db.session.query(Event).filter_by(device_id="did-test-4").first()
    assert row is not None
    assert row.event_name == "generate_start"
    assert row.keyword == "下雨天"


def test_generate_story_calls_deepseek_when_configured(client, app, monkeypatch):
    """End-to-end happy path with the network call stubbed out."""

    def fake_generate(*, keyword: str):
        assert keyword == "星星"
        return {"content": "[TITLE]星星[/TITLE][STORY]从前有颗星星[/STORY]"}

    monkeypatch.setattr(story_service, "generate", fake_generate)
    app.config["DEEPSEEK_API_KEY"] = "fake-key-for-test"

    resp = _post(
        client,
        "/api/keke/story/generate",
        {"device_id": "did-test-5", "from": "app", "keyword": "星星"},
    )
    body = resp.get_json()
    assert body["code"] == 200
    assert body["data"]["content"].startswith("[TITLE]")


@pytest.fixture(autouse=True)
def _clear_deepseek_key(app):
    """Each test starts with an empty DEEPSEEK_API_KEY unless it sets one."""
    saved = app.config.get("DEEPSEEK_API_KEY", "")
    app.config["DEEPSEEK_API_KEY"] = ""
    yield
    app.config["DEEPSEEK_API_KEY"] = saved
