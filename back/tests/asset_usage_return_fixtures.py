"""Reusable database fixtures for asset usage and return tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from flask.testing import FlaskClient
from sqlalchemy import select

from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    AssetStatus,
    DataScope,
    OperationType,
    RecordStatus,
    UsageType,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    Organization,
    OperationRequest,
    Permission,
    PublicUsageObject,
    Role,
    RoleDataScopeOrganization,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.models.asset_usage_return import AssetUsageRequest
from app.operations.registry import operation_handler_registry
from app.security.passwords import hash_password
from app.services import operation_service


_HTTP_PASSWORD = "asset-usage-return-test"


@dataclass(frozen=True)
class HttpHeaders:
    manager: dict[str, str]
    employee: dict[str, str]


@dataclass(frozen=True)
class UsageReturnContext:
    organization: Organization
    location: AssetLocation
    return_location: AssetLocation
    manager: User
    employee: User
    public_object: PublicUsageObject
    main_asset: Asset
    child_asset: Asset


@dataclass(frozen=True)
class CrossScopeUsageContext:
    base: UsageReturnContext
    applicant: User
    other_organization: Organization
    operation: OperationRequest


def seed_usage_return_context() -> UsageReturnContext:
    organization = Organization(
        code="UR-ORG",
        name="UR Organization",
        status=RecordStatus.ENABLED.value,
    )
    location = AssetLocation(
        code="UR-LOCATION",
        name="UR Location",
        status=RecordStatus.ENABLED.value,
        is_selectable=True,
    )
    return_location = AssetLocation(
        code="UR-RETURN-LOCATION",
        name="UR Return Location",
        status=RecordStatus.ENABLED.value,
        is_selectable=True,
    )
    unit = Unit(
        code="UR-UNIT",
        name="UR Unit",
        status=RecordStatus.ENABLED.value,
    )
    source = AssetSource(
        code="UR-SOURCE",
        name="UR Source",
        status=RecordStatus.ENABLED.value,
    )
    manager = User(
        username="UR-manager",
        password="x",
        nickname="UR Manager",
        enabled=True,
    )
    employee = User(
        username="UR-employee",
        password="x",
        nickname="UR Employee",
        enabled=True,
    )
    public_object = PublicUsageObject(
        code="UR-PUBLIC-OBJECT",
        name="UR Public Object",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add_all(
        [
            organization,
            location,
            return_location,
            unit,
            source,
            manager,
            employee,
            public_object,
        ]
    )
    db.session.flush()
    manager.organization_id = organization.id
    employee.organization_id = organization.id
    category = AssetCategory(
        code="UR-CATEGORY",
        name="UR Category",
        service_life_months=36,
        default_unit_id=unit.id,
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(category)
    db.session.flush()
    main_asset = Asset(
        asset_code="UR-ASSET-MAIN",
        asset_name="UR Main Asset",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("100.00"),
        purchase_date=date(2026, 7, 21),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
    )
    db.session.add(main_asset)
    db.session.flush()
    child_asset = Asset(
        asset_code="UR-ASSET-CHILD",
        asset_name="UR Child Asset",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        parent_asset_id=main_asset.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("10.00"),
        purchase_date=date(2026, 7, 21),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
    )
    db.session.add(child_asset)
    db.session.flush()
    return UsageReturnContext(
        organization=organization,
        location=location,
        return_location=return_location,
        manager=manager,
        employee=employee,
        public_object=public_object,
        main_asset=main_asset,
        child_asset=child_asset,
    )


def seed_http_context(
    client: FlaskClient,
) -> tuple[UsageReturnContext, HttpHeaders]:
    context = seed_usage_return_context()
    grant_permissions(context.manager, "asset:usage:manage")
    grant_permissions(context.employee, "asset:return:self")
    context.manager.password = hash_password(_HTTP_PASSWORD, rounds=4)
    context.employee.password = hash_password(_HTTP_PASSWORD, rounds=4)
    db.session.commit()

    tokens: dict[str, str] = {}
    for actor, username in (
        ("manager", context.manager.username),
        ("employee", context.employee.username),
    ):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": _HTTP_PASSWORD},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["code"] == 200
        tokens[actor] = body["data"]["token"]

    return context, HttpHeaders(
        manager={"Authorization": f"Bearer {tokens['manager']}"},
        employee={"Authorization": f"Bearer {tokens['employee']}"},
    )


def grant_permissions(user: User | int, *codes: str) -> Role:
    user_id = user.id if isinstance(user, User) else user
    role_code = f"UR-ALL-{user_id}"
    role = db.session.scalar(select(Role).where(Role.code == role_code))
    if role is None:
        role = Role(
            code=role_code,
            name=f"UR All Scope {user_id}",
            data_scope=DataScope.ALL.value,
            enabled=True,
        )
        db.session.add(role)
        db.session.flush()
    else:
        role.data_scope = DataScope.ALL.value
        role.enabled = True

    user_role = db.session.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
        )
    )
    if user_role is None:
        db.session.add(UserRole(user_id=user_id, role_id=role.id))

    for code in sorted(set(codes)):
        permission = db.session.scalar(
            select(Permission).where(Permission.code == code)
        )
        if permission is None:
            permission = Permission(
                code=code,
                name=code,
                module=code.split(":", maxsplit=1)[0],
                enabled=True,
            )
            db.session.add(permission)
            db.session.flush()
        else:
            permission.enabled = True
        link = db.session.scalar(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == permission.id,
            )
        )
        if link is None:
            db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.session.flush()
    return role


def grant_scoped_manager_permission(
    user: User | int,
    organization_id: int,
) -> Role:
    user_id = user.id if isinstance(user, User) else user
    role_code = f"UR-CUSTOM-{user_id}"
    role = db.session.scalar(select(Role).where(Role.code == role_code))
    if role is None:
        role = Role(
            code=role_code,
            name=f"UR Custom Scope {user_id}",
            data_scope=DataScope.CUSTOM.value,
            enabled=True,
        )
        db.session.add(role)
        db.session.flush()
    else:
        role.data_scope = DataScope.CUSTOM.value
        role.enabled = True

    user_role = db.session.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
        )
    )
    if user_role is None:
        db.session.add(UserRole(user_id=user_id, role_id=role.id))

    permission = db.session.scalar(
        select(Permission).where(Permission.code == "asset:usage:manage")
    )
    if permission is None:
        permission = Permission(
            code="asset:usage:manage",
            name="asset:usage:manage",
            module="asset",
            enabled=True,
        )
        db.session.add(permission)
        db.session.flush()
    else:
        permission.enabled = True
    role_permission = db.session.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role.id,
            RolePermission.permission_id == permission.id,
        )
    )
    if role_permission is None:
        db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    scope_link = db.session.scalar(
        select(RoleDataScopeOrganization).where(
            RoleDataScopeOrganization.role_id == role.id,
            RoleDataScopeOrganization.organization_id == organization_id,
        )
    )
    if scope_link is None:
        db.session.add(
            RoleDataScopeOrganization(
                role_id=role.id,
                organization_id=organization_id,
            )
        )
    db.session.flush()
    return role


def seed_cross_scope_usage() -> CrossScopeUsageContext:
    context = seed_usage_return_context()
    applicant = User(
        username="UR-cross-applicant",
        password="x",
        nickname="UR Cross Applicant",
        organization_id=context.organization.id,
        enabled=True,
    )
    other_organization = Organization(
        code="UR-CROSS-ORG",
        name="UR Cross Organization",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add_all([applicant, other_organization])
    db.session.flush()
    context.child_asset.organization_id = other_organization.id
    target = {
        "status": AssetStatus.IN_USE.value,
        "usage_type": UsageType.PERSONAL.value,
        "holder_user_id": context.employee.id,
        "public_object_id": None,
        "usage_department_id": context.organization.id,
        "location_id": context.location.id,
    }
    operation = operation_service.create_request(
        operation_type=OperationType.PERSONAL_USE.value,
        applicant_id=applicant.id,
        approval_channel=ApprovalChannel.FEISHU.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=[context.main_asset, context.child_asset],
        target_data_by_asset_id={
            context.main_asset.id: target,
            context.child_asset.id: target,
        },
        idempotency_key=None,
    ).operation
    db.session.add(
        AssetUsageRequest(
            operation_request_id=operation.id,
            target_user_id=context.employee.id,
            target_user_snapshot={
                "id": context.employee.id,
                "username": context.employee.username,
                "name": context.employee.nickname or context.employee.username,
            },
            target_public_object_id=None,
            target_public_object_snapshot=None,
            usage_department_id=context.organization.id,
            usage_department_snapshot={
                "id": context.organization.id,
                "code": context.organization.code,
                "name": context.organization.name,
            },
            target_location_id=context.location.id,
            target_location_snapshot={
                "id": context.location.id,
                "code": context.location.code,
                "name": context.location.name,
            },
        )
    )
    db.session.flush()
    return CrossScopeUsageContext(
        base=context,
        applicant=applicant,
        other_organization=other_organization,
        operation=operation,
    )


def register_usage_return_handlers() -> None:
    from app.operations.asset_usage_return_handlers import (
        PersonalReturnHandler,
        PersonalUsageHandler,
        PublicReturnHandler,
        PublicUsageHandler,
    )

    handlers = (
        PersonalUsageHandler(),
        PublicUsageHandler(),
        PersonalReturnHandler(),
        PublicReturnHandler(),
    )
    for handler in handlers:
        if not operation_handler_registry.contains(handler.operation_type):
            operation_handler_registry.register(handler)


__all__ = [
    "CrossScopeUsageContext",
    "HttpHeaders",
    "UsageReturnContext",
    "grant_permissions",
    "grant_scoped_manager_permission",
    "register_usage_return_handlers",
    "seed_cross_scope_usage",
    "seed_http_context",
    "seed_usage_return_context",
]
