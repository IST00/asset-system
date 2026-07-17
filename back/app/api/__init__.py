"""Register all business blueprints onto the Flask app."""

from __future__ import annotations

from flask import Flask

from app.api import (
    assets,
    auth,
    hello,
    master_data,
    organizations,
    rbac,
    stock_in,
    users,
)


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(hello.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(rbac.bp)
    app.register_blueprint(organizations.bp)
    app.register_blueprint(master_data.bp)
    app.register_blueprint(stock_in.bp)
    app.register_blueprint(assets.bp)
