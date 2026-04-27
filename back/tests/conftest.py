"""pytest fixtures: app, client, db session."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db
from config import TestConfig


@pytest.fixture(scope="session")
def app():
    app = create_app(config=TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _db_session(app):
    """Wrap each test in a transaction that is rolled back after the test."""
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()
        _db.session.configure(bind=connection)
        yield _db.session
        transaction.rollback()
        connection.close()
        _db.session.remove()
