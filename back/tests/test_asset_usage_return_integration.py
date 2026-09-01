"""Application-level wiring contracts for asset usage and return."""

from __future__ import annotations

from flask import Flask

from app import create_app
import app.models as domain_models
from app.operations import operation_handler_registry
from config import DevConfig, ProdConfig, TestConfig


_FORMAL_ROUTE_SUFFIXES = {
    "/api/v1/asset-usage-requests/personal",
    "/api/v1/asset-usage-requests/public",
    "/api/v1/asset-usage-requests",
    "/api/v1/asset-usage-requests/<int:operation_request_id>",
    "/api/v1/asset-return-requests/personal",
    "/api/v1/asset-return-requests/public",
    "/api/v1/asset-return-requests/<int:operation_request_id>/confirm",
    "/api/v1/asset-return-requests",
    "/api/v1/asset-return-requests/<int:operation_request_id>",
}
_MOCK_ROUTE_SUFFIXES = {
    "/api/v1/asset-usage-requests/<int:operation_request_id>/mock-feishu-action",
    "/api/v1/asset-return-requests/<int:operation_request_id>/mock-feishu-action",
}
_FEATURE_OPERATION_TYPES = {
    "PERSONAL_USE",
    "PUBLIC_USE",
    "PERSONAL_RETURN",
    "PUBLIC_RETURN",
}


class _DevelopmentIntegrationConfig(DevConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class _ProductionIntegrationConfig(ProdConfig):
    SECRET_KEY = "production-integration-test-secret-key-value"
    JWT_SECRET_KEY = "production-integration-test-jwt-secret-value"
    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://test_app:synthetic-password@db.invalid/" "asset_system_test"
    )
    CORS_ALLOWED_ORIGINS = "https://production.test.invalid"
    LOCAL_FEISHU_ENABLED = True


def _routes(app: Flask) -> set[str]:
    return {rule.rule for rule in app.url_map.iter_rules()}


def test_feature_models_are_registered_in_public_metadata_aggregation() -> None:
    for name in ("AssetUsageRequest", "AssetReturnRequest", "AssetReturnItem"):
        assert getattr(domain_models, name, None) is not None
        assert name in domain_models.__all__


def test_test_profile_registers_formal_mock_routes_and_all_handlers() -> None:
    operation_handler_registry.clear()

    app = create_app(config=TestConfig)

    assert _FORMAL_ROUTE_SUFFIXES | _MOCK_ROUTE_SUFFIXES <= _routes(app)
    assert all(
        operation_handler_registry.contains(operation_type)
        for operation_type in _FEATURE_OPERATION_TYPES
    )


def test_development_profile_registers_mock_routes() -> None:
    app = create_app(config=_DevelopmentIntegrationConfig)

    assert _MOCK_ROUTE_SUFFIXES <= _routes(app)


def test_production_profile_registers_formal_routes_but_never_mock_routes() -> None:
    app = create_app(config=_ProductionIntegrationConfig)
    routes = _routes(app)

    assert _FORMAL_ROUTE_SUFFIXES <= routes
    assert routes.isdisjoint(_MOCK_ROUTE_SUFFIXES)
