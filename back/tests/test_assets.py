from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import mysql

import app.services as services
from app.common import BusinessException, ResultCode
from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    ApprovalStep,
    ApprovalTask,
    InventoryItem,
    InventoryTask,
    OperationLog,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    Permission,
    Role,
    RolePermission,
    Supplier,
    Unit,
    User,
    UserRole,
)
from app.repositories.asset_repository import asset_repository
from app.security.passwords import hash_password


def _reader(
    client, username: str, scope: str, permission_codes: list[str], organization=None
):
    user = User(
        username=username,
        password=hash_password("admin123"),
        enabled=True,
        organization_id=organization.id if organization else None,
    )
    role = Role(code=f"{username.upper()}_ROLE", name=username, data_scope=scope)
    permissions = []
    for code in permission_codes:
        permission = db.session.query(Permission).filter_by(code=code).one_or_none()
        if permission is None:
            permission = Permission(code=code, name=code, module=code.split(":")[0])
            db.session.add(permission)
        permissions.append(permission)
    db.session.add_all([user, role])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login", json={"username": username, "password": "admin123"}
    ).get_json()["data"]["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _asset_fixture():
    organization = Organization(code="ASSET-ORG", name="资产公司")
    other_organization = Organization(code="OTHER-ORG", name="其他公司")
    unit = Unit(code="ASSET-UNIT", name="台")
    source = AssetSource(code="ASSET-SOURCE", name="采购")
    location = AssetLocation(code="ASSET-LOC", name="仓库", is_selectable=True)
    manager = User(username="asset-owner", password="x", enabled=True)
    db.session.add_all(
        [organization, other_organization, unit, source, location, manager]
    )
    db.session.flush()
    manager.organization_id = organization.id
    category = AssetCategory(
        code="ASSET-CATEGORY",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="ASSET-ORG-ASSET-CATEGORY-0001",
        asset_name="MacBook Air",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("8999.00"),
        purchase_date=date(2026, 7, 17),
        service_life_months=36,
        expected_expiry_date=date(2029, 1, 1),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
        normalized_serial="asset-sn",
        serial_number="ASSET-SN",
    )
    db.session.add(asset)
    db.session.flush()
    db.session.add_all(
        [
            AssetLifecycleRecord(
                asset_id=asset.id,
                operation_type="STOCK_IN",
                operation_no="STI-ASSET",
                operator_id=manager.id,
                before_data=None,
                after_data={"status": "IDLE"},
            ),
            OperationLog(
                action="STOCK_IN",
                resource_type="asset",
                resource_id=str(asset.id),
                operator_id=manager.id,
                before_data=None,
                after_data={"asset_code": asset.asset_code},
            ),
        ]
    )
    db.session.commit()
    return organization, other_organization, manager, asset


def _copy_asset(
    asset: Asset,
    *,
    asset_code: str,
    organization_id: int,
    manager_id: int,
    holder_user_id: int | None = None,
) -> Asset:
    copied = Asset(
        asset_code=asset_code,
        asset_name=f"{asset.asset_name} {asset_code}",
        status=asset.status,
        organization_id=organization_id,
        category_id=asset.category_id,
        unit_id=asset.unit_id,
        original_amount=asset.original_amount,
        purchase_date=asset.purchase_date,
        service_life_months=asset.service_life_months,
        expected_expiry_date=asset.expected_expiry_date,
        manager_id=manager_id,
        holder_user_id=holder_user_id,
        source_id=asset.source_id,
        location_id=asset.location_id,
        custom_attributes=dict(asset.custom_attributes),
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )
    db.session.add(copied)
    db.session.flush()
    return copied


def _grant_scope(user: User, scope: str, suffix: str) -> None:
    role = Role(
        code=f"{user.username.upper()}_{suffix}",
        name=f"{user.username}-{suffix}",
        data_scope=scope,
    )
    db.session.add(role)
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.commit()


def test_asset_list_applies_scope_and_amount_field_permission(client) -> None:
    organization, _other, manager, asset = _asset_fixture()
    all_user, all_headers = _reader(
        client,
        "all-reader",
        DataScope.ALL.value,
        ["asset:view", "asset:amount:view"],
    )
    self_user, self_headers = _reader(
        client,
        "self-reader",
        DataScope.SELF.value,
        ["asset:view"],
        organization,
    )
    asset.manager_id = self_user.id
    db.session.commit()

    all_result = client.get("/api/v1/assets", headers=all_headers).get_json()["data"]
    assert all_result["total"] == 1
    assert all_result["items"][0]["original_amount"] == "8999.00"

    self_result = client.get("/api/v1/assets", headers=self_headers).get_json()["data"]
    assert self_result["total"] == 1
    assert "original_amount" not in self_result["items"][0]
    assert self_result["items"][0]["asset_code"] == asset.asset_code


def test_asset_dashboard_returns_real_scoped_aggregates(client) -> None:
    organization, _other, manager, asset = _asset_fixture()
    departed_holder = User(
        username="departed-holder",
        password="x",
        enabled=False,
        organization_id=organization.id,
    )
    db.session.add(departed_holder)
    db.session.flush()
    second = _copy_asset(
        asset,
        asset_code="ASSET-DASHBOARD-SECOND",
        organization_id=organization.id,
        manager_id=manager.id,
        holder_user_id=departed_holder.id,
    )
    second.status = AssetStatus.IN_USE.value
    second.data_completeness = AssetDataCompleteness.INCOMPLETE.value
    db.session.commit()
    _user, headers = _reader(
        client,
        "dashboard-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )

    response = client.get("/api/v1/assets/dashboard", headers=headers)
    result = response.get_json()["data"]

    assert response.status_code == 200
    assert result["metrics"] == {
        "total": 2,
        "idle": 1,
        "in_use": 1,
        "repairing": 0,
        "scrapped": 0,
    }
    assert result["issues"]["incomplete_assets"] == 1
    assert result["issues"]["departed_owner_assets"] == 1
    assert result["issues"]["pending_approvals"] == 0
    assert result["categories"] == [{"name": "电脑", "value": 2}]
    assert sum(item["intake"] for item in result["monthly_changes"]) == 2
    assert sum(item["value"] for item in result["statuses"]) == 2


def test_asset_detail_lifecycle_and_audit_require_permissions(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "audit-reader",
        DataScope.ALL.value,
        ["asset:view", "audit:view"],
    )

    detail = client.get(f"/api/v1/assets/{asset.id}", headers=headers).get_json()[
        "data"
    ]
    assert detail["asset_name"] == "MacBook Air"
    lifecycle = client.get(
        f"/api/v1/assets/{asset.id}/lifecycle", headers=headers
    ).get_json()["data"]
    assert lifecycle[0]["operation_no"] == "STI-ASSET"
    audit = client.get("/api/v1/audit-logs", headers=headers).get_json()["data"]
    assert audit[0]["action"] == "STOCK_IN"


def test_asset_list_filters_by_name_and_normalized_serial(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "filter-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )

    by_name = client.get(
        "/api/v1/assets",
        headers=headers,
        query_string={"asset_name": "MacBook"},
    ).get_json()["data"]
    assert by_name["total"] == 1
    assert by_name["items"][0]["id"] == asset.id

    by_serial = client.get(
        "/api/v1/assets",
        headers=headers,
        query_string={"serial_number": " asset-SN "},
    ).get_json()["data"]
    assert by_serial["total"] == 1
    assert by_serial["items"][0]["id"] == asset.id

    missing = client.get(
        "/api/v1/assets",
        headers=headers,
        query_string={"asset_name": "不存在"},
    ).get_json()["data"]
    assert missing["total"] == 0


def test_asset_data_service_is_exported_with_completeness_helpers() -> None:
    assert "calculate_completeness_values" in services.asset_data_service.__all__
    assert "missing_fields" in services.asset_data_service.__all__


def test_self_scope_includes_holder_and_manager_but_hides_other_assets(client) -> None:
    organization, _other, manager, asset = _asset_fixture()
    self_user, headers = _reader(
        client,
        "self-holder-reader",
        DataScope.SELF.value,
        ["asset:view"],
        organization,
    )

    asset.manager_id = manager.id
    asset.holder_user_id = self_user.id
    db.session.commit()
    held = client.get("/api/v1/assets", headers=headers).get_json()["data"]
    assert [item["id"] for item in held["items"]] == [asset.id]

    asset.holder_user_id = None
    asset.manager_id = self_user.id
    db.session.commit()
    managed = client.get("/api/v1/assets", headers=headers).get_json()["data"]
    assert [item["id"] for item in managed["items"]] == [asset.id]

    asset.manager_id = manager.id
    db.session.commit()
    hidden = client.get("/api/v1/assets", headers=headers).get_json()["data"]
    assert hidden["total"] == 0
    detail = client.get(f"/api/v1/assets/{asset.id}", headers=headers).get_json()
    lifecycle = client.get(
        f"/api/v1/assets/{asset.id}/lifecycle", headers=headers
    ).get_json()
    assert detail["code"] == ResultCode.NOT_FOUND.code
    assert lifecycle["code"] == ResultCode.NOT_FOUND.code
    assert detail["message"] == lifecycle["message"] == "资产不存在"


def test_department_and_self_scopes_are_combined_with_or(client) -> None:
    organization, other_organization, manager, department_asset = _asset_fixture()
    reader, headers = _reader(
        client,
        "department-self-reader",
        DataScope.DEPARTMENT.value,
        ["asset:view"],
        organization,
    )
    _grant_scope(reader, DataScope.SELF.value, "SELF_ROLE")
    self_asset = _copy_asset(
        department_asset,
        asset_code="ASSET-CROSS-SELF",
        organization_id=other_organization.id,
        manager_id=manager.id,
        holder_user_id=reader.id,
    )
    hidden_asset = _copy_asset(
        department_asset,
        asset_code="ASSET-CROSS-HIDDEN",
        organization_id=other_organization.id,
        manager_id=manager.id,
    )
    db.session.commit()

    result = client.get("/api/v1/assets", headers=headers).get_json()["data"]

    assert [item["id"] for item in result["items"]] == [
        department_asset.id,
        self_asset.id,
    ]
    assert hidden_asset.id not in {item["id"] for item in result["items"]}


def test_all_scope_sees_everything_and_empty_usable_scope_sees_nothing(client) -> None:
    _organization, other_organization, manager, asset = _asset_fixture()
    second = _copy_asset(
        asset,
        asset_code="ASSET-ALL-SECOND",
        organization_id=other_organization.id,
        manager_id=manager.id,
    )
    db.session.commit()
    _all_user, all_headers = _reader(
        client,
        "all-scope-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )
    _empty_user, empty_headers = _reader(
        client,
        "empty-scope-reader",
        DataScope.DEPARTMENT.value,
        ["asset:view"],
    )

    all_result = client.get("/api/v1/assets", headers=all_headers).get_json()["data"]
    empty_result = client.get("/api/v1/assets", headers=empty_headers).get_json()[
        "data"
    ]

    assert [item["id"] for item in all_result["items"]] == [asset.id, second.id]
    assert empty_result["total"] == 0
    assert empty_result["items"] == []


def test_get_accessible_checks_permission_then_hides_out_of_scope_assets(
    client,
) -> None:
    organization, other_organization, _manager, asset = _asset_fixture()
    denied_user, _denied_headers = _reader(
        client,
        "denied-access-reader",
        DataScope.DEPARTMENT.value,
        [],
        other_organization,
    )
    scoped_user, _scoped_headers = _reader(
        client,
        "scoped-access-reader",
        DataScope.DEPARTMENT.value,
        ["asset:view"],
        other_organization,
    )
    assert organization.id != other_organization.id
    access_service = getattr(services, "asset_access_service", None)
    assert access_service is not None, "missing asset_access_service"

    with pytest.raises(BusinessException) as forbidden:
        access_service.get_accessible(asset.id, denied_user.id)
    assert forbidden.value.code == ResultCode.FORBIDDEN.code

    with pytest.raises(BusinessException) as out_of_scope:
        access_service.get_accessible(asset.id, scoped_user.id)
    with pytest.raises(BusinessException) as absent:
        access_service.get_accessible(asset.id + 10_000, scoped_user.id)
    assert out_of_scope.value.code == absent.value.code == ResultCode.NOT_FOUND.code
    assert out_of_scope.value.message == absent.value.message == "资产不存在"


def test_asset_repository_filters_deduplicates_sorts_and_locks(
    app, monkeypatch
) -> None:
    organization, other_organization, manager, asset = _asset_fixture()
    allowed = _copy_asset(
        asset,
        asset_code="ASSET-REPOSITORY-ALLOWED",
        organization_id=organization.id,
        manager_id=manager.id,
    )
    blocked = _copy_asset(
        asset,
        asset_code="ASSET-REPOSITORY-BLOCKED",
        organization_id=other_organization.id,
        manager_id=manager.id,
    )
    db.session.commit()
    find_many = getattr(asset_repository, "find_many_accessible_for_update", None)
    assert find_many is not None, "missing find_many_accessible_for_update"
    assert find_many([], Asset.id.is_not(None)) == []

    statements = []
    session = db.session()
    original_scalars = session.scalars

    def recording_scalars(statement, *args, **kwargs):
        statements.append(statement)
        return original_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(session, "scalars", recording_scalars)
    result = find_many(
        [blocked.id, allowed.id, asset.id, allowed.id],
        Asset.organization_id == organization.id,
    )

    assert [item.id for item in result] == [asset.id, allowed.id]
    assert len(statements) == 1
    compiled = " ".join(
        str(
            statements[0].compile(
                dialect=mysql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).split()
    )
    expected_ids = ", ".join(
        str(asset_id) for asset_id in sorted({asset.id, allowed.id, blocked.id})
    )
    assert f"assets.id IN ({expected_ids})" in compiled
    assert "ORDER BY assets.id ASC" in compiled
    assert compiled.endswith("FOR UPDATE")


def test_asset_outputs_include_data_fields_and_copy_custom_attributes(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    supplier = Supplier(code="SUP-ASSET", name="资产供应商")
    db.session.add(supplier)
    db.session.flush()
    asset.supplier_id = supplier.id
    asset.custom_attributes = {"color": "space-gray"}
    db.session.commit()
    user, headers = _reader(
        client,
        "asset-output-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )

    listed = client.get("/api/v1/assets", headers=headers).get_json()["data"]["items"][
        0
    ]
    detail = client.get(f"/api/v1/assets/{asset.id}", headers=headers).get_json()[
        "data"
    ]
    expected = {
        "supplier_id": supplier.id,
        "service_life_months": 36,
        "expected_expiry_date": "2029-01-01",
        "custom_attributes": {"color": "space-gray"},
        "data_completeness": AssetDataCompleteness.COMPLETE.value,
        "missing_fields": [],
    }
    for payload in (listed, detail):
        assert {name: payload[name] for name in expected} == expected
        assert "original_amount" not in payload

    service_detail = services.asset_service.get(asset.id, user.id)
    assert service_detail["custom_attributes"] is not asset.custom_attributes
    service_detail["custom_attributes"]["mutated"] = True
    assert "mutated" not in asset.custom_attributes


def test_asset_page_filters_completeness_in_sql_and_rejects_invalid_value(
    client,
) -> None:
    _organization, _other, manager, complete_asset = _asset_fixture()
    incomplete_asset = _copy_asset(
        complete_asset,
        asset_code="ASSET-INCOMPLETE",
        organization_id=complete_asset.organization_id,
        manager_id=manager.id,
    )
    incomplete_asset.unit_id = None
    incomplete_asset.data_completeness = AssetDataCompleteness.INCOMPLETE.value
    db.session.commit()
    _user, headers = _reader(
        client,
        "completeness-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )
    statements: list[str] = []

    def capture_statement(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if "FROM assets" in statement:
            statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", capture_statement)
    try:
        complete_response = client.get(
            "/api/v1/assets",
            headers=headers,
            query_string={"data_completeness": AssetDataCompleteness.COMPLETE.value},
        )
        complete_statements = tuple(statements)
        statements.clear()
        incomplete_response = client.get(
            "/api/v1/assets",
            headers=headers,
            query_string={"data_completeness": AssetDataCompleteness.INCOMPLETE.value},
        )
        incomplete_statements = tuple(statements)
    finally:
        event.remove(db.engine, "before_cursor_execute", capture_statement)

    assert complete_response.status_code == 200
    assert incomplete_response.status_code == 200
    complete = complete_response.get_json()["data"]
    incomplete = incomplete_response.get_json()["data"]
    assert [item["id"] for item in complete["items"]] == [complete_asset.id]
    assert [item["id"] for item in incomplete["items"]] == [incomplete_asset.id]
    assert incomplete["items"][0]["missing_fields"] == ["unit_id"]
    for request_statements in (complete_statements, incomplete_statements):
        assert len(request_statements) == 2
        assert all(
            "assets.data_completeness" in statement and "WHERE" in statement
            for statement in request_statements
        )

    invalid = client.get(
        "/api/v1/assets",
        headers=headers,
        query_string={"data_completeness": "UNKNOWN"},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["code"] == ResultCode.BAD_REQUEST.code


def test_asset_get_and_lifecycle_delegate_to_access_service(
    client, monkeypatch
) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    user, _headers = _reader(
        client,
        "access-delegation-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )
    access_service = getattr(services, "asset_access_service", None)
    assert access_service is not None, "missing asset_access_service"
    original_get_accessible = access_service.get_accessible
    calls: list[tuple[int, int, str]] = []

    def recording_get_accessible(
        asset_id: int,
        actor_id: int,
        permission_code: str = "asset:view",
    ) -> Asset:
        calls.append((asset_id, actor_id, permission_code))
        return original_get_accessible(asset_id, actor_id, permission_code)

    monkeypatch.setattr(access_service, "get_accessible", recording_get_accessible)

    services.asset_service.get(asset.id, user.id)
    services.asset_service.lifecycle(asset.id, user.id)

    assert calls == [
        (asset.id, user.id, "asset:view"),
        (asset.id, user.id, "asset:view"),
    ]
    assert not hasattr(services.asset_service, "_access_filter")


def test_asset_related_records_returns_real_operations_approvals_and_inventory(
    client,
) -> None:
    organization, _other, manager, asset = _asset_fixture()
    approver = User(
        username="asset-related-approver",
        password="x",
        nickname="审批负责人",
        enabled=True,
    )
    db.session.add(approver)
    db.session.flush()
    now = datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc)
    operation = OperationRequest(
        request_no="OP-RELATED-001",
        operation_type="TRANSFER",
        applicant_id=manager.id,
        approval_channel="INTERNAL",
        approval_status="APPROVED",
        execution_status="SUCCESS",
        submitted_at=now,
        approved_at=now,
        executed_at=now,
    )
    db.session.add(operation)
    db.session.flush()
    request_asset = OperationRequestAsset(
        operation_request_id=operation.id,
        asset_id=asset.id,
        asset_code_snapshot=asset.asset_code,
        asset_name_snapshot=asset.asset_name,
        asset_status_snapshot=asset.status,
        asset_version_snapshot=asset.version,
        organization_id_snapshot=asset.organization_id,
        before_data={"location_name": "仓库"},
        target_data={"location_name": "研发中心"},
    )
    step = ApprovalStep(
        operation_request_id=operation.id,
        level_no=1,
        sign_mode="OR_SIGN",
        status="APPROVED",
    )
    db.session.add_all([request_asset, step])
    db.session.flush()
    approval_task = ApprovalTask(
        approval_step_id=step.id,
        approver_id=approver.id,
        status="APPROVED",
        opinion="同意调拨",
        decided_at=now,
    )
    inventory_task = InventoryTask(
        task_no="INV-RELATED-001",
        name="研发设备季度盘点",
        status="COMPLETED",
        deadline_at=datetime(2026, 8, 10, 15, 59, tzinfo=timezone.utc),
        created_by=manager.id,
        scope_filters={"organization_ids": [organization.id]},
    )
    db.session.add_all([approval_task, inventory_task])
    db.session.flush()
    inventory_item = InventoryItem(
        task_id=inventory_task.id,
        asset_id=asset.id,
        responsible_user_id=manager.id,
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        asset_status_snapshot=asset.status,
        organization_id=organization.id,
        organization_name=organization.name,
        category_id=asset.category_id,
        category_name="电脑",
        ledger_location_id=asset.location_id,
        ledger_location_name="仓库",
        status="FOUND",
        physical_result="FOUND",
        location_result="MISMATCH",
        actual_location_text="研发中心 A 区",
        submission_method="MANUAL",
        submitted_by=manager.id,
        submitted_at=now,
        is_late=False,
        review_status="CONFIRMED",
        resolution="UPDATE_LOCATION",
        resolution_reason="现场地点已核实",
    )
    db.session.add(inventory_item)
    db.session.commit()
    _, headers = _reader(
        client,
        "asset-related-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )

    response = client.get(
        f"/api/v1/assets/{asset.id}/related-records",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == 200
    related = body["data"]
    assert len(related["operations"]) == 1
    operation_data = related["operations"][0]
    assert operation_data["request_no"] == "OP-RELATED-001"
    assert operation_data["applicant_name"] == manager.username
    assert operation_data["before_data"] == {"location_name": "仓库"}
    assert operation_data["target_data"] == {"location_name": "研发中心"}
    assert operation_data["approval_steps"][0]["status"] == "APPROVED"
    approval_data = operation_data["approval_steps"][0]["tasks"][0]
    assert approval_data["approver_name"] == "审批负责人"
    assert approval_data["opinion"] == "同意调拨"

    assert len(related["inventory_records"]) == 1
    inventory_data = related["inventory_records"][0]
    assert inventory_data["task_no"] == "INV-RELATED-001"
    assert inventory_data["physical_result"] == "FOUND"
    assert inventory_data["location_result"] == "MISMATCH"
    assert inventory_data["actual_location_text"] == "研发中心 A 区"
    assert inventory_data["submitted_by_name"] == manager.username
    assert inventory_data["resolution"] == "UPDATE_LOCATION"


def test_asset_related_records_enforces_permission_and_asset_data_scope(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _, no_permission_headers = _reader(
        client,
        "asset-related-no-permission",
        DataScope.ALL.value,
        [],
    )
    _, self_scope_headers = _reader(
        client,
        "asset-related-self-scope",
        DataScope.SELF.value,
        ["asset:view"],
    )

    forbidden = client.get(
        f"/api/v1/assets/{asset.id}/related-records",
        headers=no_permission_headers,
    )
    hidden = client.get(
        f"/api/v1/assets/{asset.id}/related-records",
        headers=self_scope_headers,
    )

    assert forbidden.status_code == 200
    assert forbidden.get_json()["code"] == ResultCode.FORBIDDEN.code
    assert hidden.status_code == 200
    assert hidden.get_json()["code"] == ResultCode.NOT_FOUND.code


def test_repair_and_scrap_reasons_are_persisted_in_asset_lifecycle(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _, headers = _reader(
        client,
        "asset-lifecycle-operator",
        DataScope.ALL.value,
        ["asset:view", "asset:repair", "asset:scrap"],
    )

    repair_started = client.post(
        "/api/v1/asset-actions/repair/start",
        headers=headers,
        json={
            "items": [{"asset_id": asset.id, "version": asset.version}],
            "vendor": "苹果授权维修中心",
            "estimated_cost": "680.00",
            "reason": "设备无法正常启动",
        },
    ).get_json()
    assert repair_started["code"] == 200
    repairing_asset = repair_started["data"]["items"][0]

    repair_completed = client.post(
        "/api/v1/asset-actions/repair/complete",
        headers=headers,
        json={
            "items": [{"asset_id": asset.id, "version": repairing_asset["version"]}],
            "actual_cost": "620.00",
            "result": "更换主板后测试通过",
        },
    ).get_json()
    assert repair_completed["code"] == 200
    repaired_asset = repair_completed["data"]["items"][0]

    scrapped = client.post(
        "/api/v1/asset-actions/scrap",
        headers=headers,
        json={
            "items": [{"asset_id": asset.id, "version": repaired_asset["version"]}],
            "scrap_date": "2026-08-03",
            "scrap_amount": "300.00",
            "child_action": "BLOCK",
            "reason": "设备超过维修价值，批准报废",
        },
    ).get_json()
    assert scrapped["code"] == 200

    lifecycle = db.session.scalars(
        select(AssetLifecycleRecord)
        .where(
            AssetLifecycleRecord.asset_id == asset.id,
            AssetLifecycleRecord.operation_type.in_(
                ["REPAIR_START", "REPAIR_COMPLETE", "SCRAP"]
            ),
        )
        .order_by(AssetLifecycleRecord.id.asc())
    ).all()

    assert [(item.operation_type, item.remark) for item in lifecycle] == [
        ("REPAIR_START", "设备无法正常启动"),
        ("REPAIR_COMPLETE", "更换主板后测试通过"),
        ("SCRAP", "设备超过维修价值，批准报废"),
    ]
