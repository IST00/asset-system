"""pytest fixtures: app, client, db session."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(config=TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
