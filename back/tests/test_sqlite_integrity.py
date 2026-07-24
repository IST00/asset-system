from sqlalchemy import text

from app.extensions import db


def test_sqlite_connections_enforce_foreign_keys(app) -> None:
    enabled = db.session.execute(text("PRAGMA foreign_keys")).scalar_one()
    assert enabled == 1
