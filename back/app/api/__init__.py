"""Register all business blueprints onto the Flask app."""

from __future__ import annotations

from flask import Flask

from app.api import (
    approval_flows,
    asset_labels,
    attachments,
    exports,
    feishu,
    asset_management,
    asset_information_changes,
    asset_returns,
    asset_usage,
    assets,
    auth,
    hello,
    inventory,
    imports,
    master_data,
    notifications,
    local_feishu,
    organizations,
    operations,
    rbac,
    security_events,
    stock_in,
    suppliers,
    system_status,
    users,
    workbench,
)


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(hello.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(rbac.bp)
    app.register_blueprint(approval_flows.bp)
    app.register_blueprint(attachments.bp)
    app.register_blueprint(asset_labels.bp)
    app.register_blueprint(exports.bp)
    app.register_blueprint(feishu.bp)
    app.register_blueprint(operations.bp)
    app.register_blueprint(organizations.bp)
    app.register_blueprint(master_data.bp)
    app.register_blueprint(suppliers.bp)
    app.register_blueprint(security_events.bp)
    app.register_blueprint(system_status.bp)
    app.register_blueprint(stock_in.bp)
    app.register_blueprint(assets.bp)
    app.register_blueprint(asset_management.bp)
    app.register_blueprint(asset_information_changes.bp)
    app.register_blueprint(inventory.bp)
    app.register_blueprint(imports.bp)
    app.register_blueprint(asset_usage.bp)
    app.register_blueprint(asset_returns.bp)
    app.register_blueprint(workbench.bp)
    app.register_blueprint(notifications.bp)
    if app.testing or app.debug:
        app.register_blueprint(local_feishu.bp)
