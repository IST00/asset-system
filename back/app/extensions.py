"""Shared Flask extension instances.

Kept separate from the factory to avoid circular imports — blueprints,
models, and services import from here.
"""

from __future__ import annotations

from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_smorest import Api
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
api = Api()
