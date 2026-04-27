"""Register all business blueprints onto the Flask app."""

from __future__ import annotations

from flask import Flask

from app.api import auth, hello, users


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(hello.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(users.bp)
