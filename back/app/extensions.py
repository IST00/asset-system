"""Shared Flask extension instances.

Kept separate from the factory to avoid circular imports — blueprints,
models, and services import from here.
"""

from __future__ import annotations

import sqlite3

from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_smorest import Api
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import UnboundExecutionError
from sqlalchemy.pool import ConnectionPoolEntry


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection,
    _connection_record: ConnectionPoolEntry,
) -> None:
    """Make SQLite enforce the same declared foreign keys as MySQL."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class Database(SQLAlchemy):
    """SQLAlchemy extension with a safe SQLite schema-teardown window."""

    def drop_all(self, bind_key: str | None | list[str | None] = "__all__") -> None:
        if bind_key == "__all__":
            keys: list[str | None] = list(self.metadatas)
        elif bind_key is None or isinstance(bind_key, str):
            keys = [bind_key]
        else:
            keys = bind_key

        for key in keys:
            try:
                engine = self.engines[key]
            except KeyError:
                message = f"Bind key '{key}' is not configured."
                raise UnboundExecutionError(message) from None
            metadata = self.metadatas[key]
            if engine.dialect.name != "sqlite":
                metadata.drop_all(bind=engine)
                continue
            with engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.commit()
                try:
                    metadata.drop_all(bind=connection)
                    connection.commit()
                finally:
                    if connection.in_transaction():
                        connection.rollback()
                    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                    connection.commit()


db = Database()
migrate = Migrate()
jwt = JWTManager()
api = Api()
