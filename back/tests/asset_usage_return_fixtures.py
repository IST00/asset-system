"""Reusable database fixtures for asset usage and return tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.enums import AssetStatus, DataScope, RecordStatus
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    Organization,
    Permission,
    PublicUsageObject,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.operations.registry import operation_handler_registry


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
    "UsageReturnContext",
    "grant_permissions",
    "register_usage_return_handlers",
    "seed_usage_return_context",
]
