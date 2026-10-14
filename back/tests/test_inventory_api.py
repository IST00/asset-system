from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from sqlalchemy import select
from zipfile import ZipFile

from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetLifecycleRecord,
    AssetCategory,
    AssetLocation,
    AssetSource,
    InventoryReminder,
    InventoryScanEvent,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.security.passwords import hash_password


def _login(client, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "admin123"},
    )
    token = response.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _inventory_fixture(client):
    organization = Organization(code="INV-ORG", name="盘点公司")
    unit = Unit(code="INV-UNIT", name="台")
    source = AssetSource(code="INV-SOURCE", name="采购")
    location = AssetLocation(code="INV-LOC", name="上海办公室 3 楼", is_selectable=True)
    db.session.add_all([organization, unit, source, location])
    db.session.flush()
    category = AssetCategory(
        code="INV-CATEGORY",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    admin = User(
        username="inventory-admin",
        password=hash_password("admin123"),
        nickname="盘点管理员",
        organization_id=organization.id,
        enabled=True,
    )
    employee = User(
        username="inventory-employee",
        password=hash_password("admin123"),
        nickname="盘点员工",
        organization_id=organization.id,
        enabled=True,
    )
    db.session.add_all([category, admin, employee])
    db.session.flush()

    permissions = {
        code: Permission(code=code, name=code, module=code.split(":")[0])
        for code in ["asset:view", "inventory:view", "inventory:create"]
    }
    admin_role = Role(
        code="INVENTORY_ADMIN_TEST", name="盘点管理员", data_scope=DataScope.ALL.value
    )
    employee_role = Role(
        code="INVENTORY_EMPLOYEE_TEST",
        name="盘点员工",
        data_scope=DataScope.SELF.value,
    )
    db.session.add_all([*permissions.values(), admin_role, employee_role])
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=admin.id, role_id=admin_role.id),
            UserRole(user_id=employee.id, role_id=employee_role.id),
            *[
                RolePermission(role_id=admin_role.id, permission_id=permission.id)
                for permission in permissions.values()
            ],
            RolePermission(
                role_id=employee_role.id,
                permission_id=permissions["inventory:view"].id,
            ),
        ]
    )
    asset = Asset(
        asset_code="INV-ASSET-0001",
        asset_name="MacBook Pro",
        status=AssetStatus.IN_USE.value,
        organization_id=organization.id,
        holder_user_id=employee.id,
        usage_department_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("12999.00"),
        purchase_date=date(2026, 7, 1),
        service_life_months=36,
        expected_expiry_date=date(2029, 7, 1),
        manager_id=admin.id,
        source_id=source.id,
        location_id=location.id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
        normalized_serial="inventory-asset-sn-1",
        serial_number="INVENTORY-ASSET-SN-1",
    )
    db.session.add(asset)
    db.session.commit()
    return {
        "admin": admin,
        "employee": employee,
        "asset": asset,
        "organization": organization,
        "category": category,
        "unit": unit,
        "source": source,
        "location": location,
        "admin_headers": _login(client, admin.username),
        "employee_headers": _login(client, employee.username),
    }


def _create_task(client, fixture, *, publish: bool = True):
    response = client.post(
        "/api/v1/inventory/tasks",
        headers=fixture["admin_headers"],
        json={
            "name": "2026 年第三季度资产盘点",
            "deadline_at": "2030-01-01T00:00:00+00:00",
            "admin_user_ids": [fixture["admin"].id],
            "organization_ids": [fixture["organization"].id],
            "location_ids": [],
            "category_ids": [],
            "holder_user_ids": [],
            "public_responsible_user_id": fixture["employee"].id,
            "photo_source_mode": "CAMERA_OR_ALBUM",
            "min_photo_count": 1,
            "publish": publish,
        },
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def _task_items(client, task_id: int, headers: dict[str, str]):
    response = client.get(f"/api/v1/inventory/tasks/{task_id}/items", headers=headers)
    assert response.status_code == 200
    return response.get_json()["data"]["items"]


def _submit_found(client, fixture, task: dict, item: dict) -> dict:
    scanned = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/scan",
        headers=fixture["employee_headers"],
        json={"scanned_value": item["asset_code"]},
    )
    assert scanned.status_code == 200
    assert scanned.get_json()["data"]["outcome"] == "MATCHED"
    uploaded = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/photos",
        headers=fixture["employee_headers"],
        data={"file": (BytesIO(b"inventory-photo"), "现场照片.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200
    photo_id = uploaded.get_json()["data"]["id"]
    submitted = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/submit",
        headers=fixture["employee_headers"],
        json={
            "result": "FOUND",
            "scanned_value": item["asset_code"],
            "actual_location_id": fixture["location"].id,
            "photo_ids": [photo_id],
        },
    )
    assert submitted.status_code == 200
    return submitted.get_json()["data"]


def test_create_task_snapshots_assets_and_employee_only_sees_assigned_task(
    client,
) -> None:
    fixture = _inventory_fixture(client)
    task = _create_task(client, fixture)

    assert task["counts"]["total"] == 1
    items = _task_items(client, task["id"], fixture["employee_headers"])
    assert len(items) == 1
    assert items[0]["asset_code"] == fixture["asset"].asset_code
    assert items[0]["responsible_user_id"] == fixture["employee"].id

    tasks = client.get(
        "/api/v1/inventory/tasks", headers=fixture["employee_headers"]
    ).get_json()["data"]
    assert [item["id"] for item in tasks["items"]] == [task["id"]]


def test_found_submission_requires_scan_photo_and_location_and_can_be_returned(
    client,
) -> None:
    fixture = _inventory_fixture(client)
    task = _create_task(client, fixture)
    item = _task_items(client, task["id"], fixture["employee_headers"])[0]

    rejected = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/submit",
        headers=fixture["employee_headers"],
        json={
            "result": "FOUND",
            "scanned_value": fixture["asset"].asset_code,
            "actual_location_id": fixture["location"].id,
            "photo_ids": [],
        },
    )
    assert rejected.get_json()["code"] != 200
    assert rejected.get_json()["message"] == "请先真实扫描资产标签"

    scanned = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/scan",
        headers=fixture["employee_headers"],
        json={"scanned_value": fixture["asset"].asset_code},
    ).get_json()["data"]
    assert scanned["outcome"] == "MATCHED"

    uploaded = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/photos",
        headers=fixture["employee_headers"],
        data={"file": (BytesIO(b"inventory-photo"), "现场照片.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200
    photo_id = uploaded.get_json()["data"]["id"]

    submitted = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/submit",
        headers=fixture["employee_headers"],
        json={
            "result": "FOUND",
            "scanned_value": fixture["asset"].asset_code,
            "actual_location_id": fixture["location"].id,
            "photo_ids": [photo_id],
        },
    )
    assert submitted.status_code == 200
    submitted_item = submitted.get_json()["data"]
    assert submitted_item["status"] == "FOUND"
    assert submitted_item["location_result"] == "MATCHED"
    assert submitted_item["review_status"] == "AUTO_CONFIRMED"

    returned = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/return",
        headers=fixture["admin_headers"],
        json={"reason": "现场照片无法辨认资产标签，请重新提交"},
    )
    assert returned.status_code == 200
    returned_item = returned.get_json()["data"]
    assert returned_item["status"] == "PENDING"
    assert returned_item["review_status"] == "RETURNED"
    assert returned_item["can_submit"] is True
    assert len(returned_item["photos"]) == 1


def test_admin_mark_requires_reason_and_end_collection_does_not_auto_mark_loss(
    client,
) -> None:
    fixture = _inventory_fixture(client)
    task = _create_task(client, fixture)
    item = _task_items(client, task["id"], fixture["admin_headers"])[0]

    rejected = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/admin-mark",
        headers=fixture["admin_headers"],
        json={"item_ids": [item["id"]], "reason": ""},
    )
    assert rejected.get_json()["code"] == 400

    ended = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/end-collection",
        headers=fixture["admin_headers"],
        json={"confirm_unsubmitted_count": 1},
    )
    assert ended.status_code == 200
    ended_task = ended.get_json()["data"]
    assert ended_task["status"] == "REVIEWING"
    assert ended_task["counts"]["unsubmitted"] == 1
    assert ended_task["counts"]["loss"] == 0

    resolved = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/resolve",
        headers=fixture["admin_headers"],
        json={"resolution": "EXEMPTED", "reason": "资产已在任务发布前进入报废审批"},
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["status"] == "EXEMPTED"

    completed = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/complete",
        headers=fixture["admin_headers"],
    )
    assert completed.status_code == 200
    assert completed.get_json()["data"]["status"] == "COMPLETED"

    lifecycle_rows = db.session.scalars(
        select(AssetLifecycleRecord).where(
            AssetLifecycleRecord.asset_id == fixture["asset"].id,
            AssetLifecycleRecord.operation_type == "INVENTORY_PROCESS",
        )
    ).all()
    assert len(lifecycle_rows) == 1
    assert lifecycle_rows[0].operation_no == task["task_no"]
    assert "盘点单号" in lifecycle_rows[0].remark


def test_outside_scope_scan_is_persisted_as_anomaly(client) -> None:
    fixture = _inventory_fixture(client)
    task = _create_task(client, fixture)
    outside_asset = Asset(
        asset_code="INV-ASSET-OUTSIDE",
        asset_name="任务外显示器",
        status=AssetStatus.IN_USE.value,
        organization_id=fixture["organization"].id,
        holder_user_id=fixture["employee"].id,
        usage_department_id=fixture["organization"].id,
        category_id=fixture["category"].id,
        unit_id=fixture["unit"].id,
        original_amount=Decimal("1999.00"),
        purchase_date=date(2026, 7, 2),
        service_life_months=36,
        expected_expiry_date=date(2029, 7, 2),
        manager_id=fixture["admin"].id,
        source_id=fixture["source"].id,
        location_id=fixture["location"].id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
        normalized_serial="inventory-asset-sn-outside",
        serial_number="INVENTORY-ASSET-SN-OUTSIDE",
    )
    db.session.add(outside_asset)
    db.session.commit()

    response = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/scan",
        headers=fixture["employee_headers"],
        json={"scanned_value": outside_asset.asset_code},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["outcome"] == "OUTSIDE_SCOPE"
    event = db.session.query(InventoryScanEvent).filter_by(task_id=task["id"]).one()
    assert event.outcome == "OUTSIDE_SCOPE"
    assert event.asset_id == outside_asset.id
    listed = client.get(
        f"/api/v1/inventory/tasks/{task['id']}/scan-events",
        headers=fixture["admin_headers"],
    )
    assert listed.status_code == 200
    listed_events = listed.get_json()["data"]
    assert listed_events["total"] == 1
    assert listed_events["items"][0]["asset_name"] == outside_asset.asset_name


def test_dashboard_and_inventory_overview_use_real_task_counts(client) -> None:
    fixture = _inventory_fixture(client)
    _create_task(client, fixture)

    overview = client.get(
        "/api/v1/inventory/overview", headers=fixture["admin_headers"]
    ).get_json()["data"]
    assert overview["active_tasks"] == 1
    assert overview["pending_assets"] == 1
    assert overview["total_assets"] == 1

    dashboard = client.get(
        "/api/v1/assets/dashboard", headers=fixture["admin_headers"]
    ).get_json()["data"]
    assert dashboard["inventory"]["total"] == 1
    assert dashboard["inventory"]["checked"] == 0
    assert dashboard["inventory"]["task_name"] == "2026 年第三季度资产盘点"


def test_inventory_admins_deadline_and_responsibility_can_be_adjusted(client) -> None:
    fixture = _inventory_fixture(client)
    task = _create_task(client, fixture)
    item = _task_items(client, task["id"], fixture["admin_headers"])[0]

    admins = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/admins",
        headers=fixture["admin_headers"],
        json={
            "admin_user_ids": [fixture["admin"].id, fixture["employee"].id],
            "reason": "增加现场协同管理员",
        },
    )
    assert admins.status_code == 200
    assert admins.get_json()["data"]["admin_user_ids"] == sorted(
        [fixture["admin"].id, fixture["employee"].id]
    )

    deadline = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/deadline",
        headers=fixture["admin_headers"],
        json={
            "deadline_at": "2031-06-30T10:30:00+08:00",
            "reason": "办公区封闭，盘点窗口顺延",
        },
    )
    assert deadline.status_code == 200
    assert deadline.get_json()["data"]["deadline_at"].startswith("2031-06-30")

    transferred = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/responsible",
        headers=fixture["admin_headers"],
        json={
            "responsible_user_id": fixture["admin"].id,
            "reason": "公共区域由管理员现场盘点",
        },
    )
    assert transferred.status_code == 200
    assert transferred.get_json()["data"]["responsible_user_id"] == fixture["admin"].id
    versions = client.get(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/versions",
        headers=fixture["admin_headers"],
    ).get_json()["data"]
    assert versions[0]["action"] == "RESPONSIBILITY_TRANSFER"


def test_employee_can_withdraw_scanned_result_and_keep_versions(client) -> None:
    fixture = _inventory_fixture(client)
    task = _create_task(client, fixture)
    item = _task_items(client, task["id"], fixture["employee_headers"])[0]
    submitted = _submit_found(client, fixture, task, item)
    assert submitted["status"] == "FOUND"
    assert submitted["result_version_count"] == 1

    withdrawn = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/withdraw",
        headers=fixture["employee_headers"],
        json={"reason": "现场地点选择错误，需要重新扫码"},
    )
    assert withdrawn.status_code == 200
    withdrawn_item = withdrawn.get_json()["data"]
    assert withdrawn_item["status"] == "PENDING"
    assert withdrawn_item["submission_method"] is None
    assert withdrawn_item["result_version_count"] == 2

    versions = client.get(
        f"/api/v1/inventory/tasks/{task['id']}/items/{item['id']}/versions",
        headers=fixture["employee_headers"],
    )
    assert versions.status_code == 200
    assert [version["action"] for version in versions.get_json()["data"]] == [
        "WITHDRAW",
        "SUBMIT",
    ]


def test_surplus_decision_reminders_and_multisheet_report(client) -> None:
    fixture = _inventory_fixture(client)
    task = _create_task(client, fixture)

    outside_asset = Asset(
        asset_code="INV-ASSET-SURPLUS",
        asset_name="盘盈候选显示器",
        status=AssetStatus.IDLE.value,
        organization_id=fixture["organization"].id,
        holder_user_id=fixture["employee"].id,
        usage_department_id=fixture["organization"].id,
        category_id=fixture["category"].id,
        unit_id=fixture["unit"].id,
        original_amount=Decimal("2199.00"),
        purchase_date=date(2026, 7, 3),
        service_life_months=36,
        expected_expiry_date=date(2029, 7, 3),
        manager_id=fixture["admin"].id,
        source_id=fixture["source"].id,
        location_id=fixture["location"].id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
        normalized_serial="inventory-asset-sn-surplus",
        serial_number="INVENTORY-ASSET-SN-SURPLUS",
    )
    db.session.add(outside_asset)
    db.session.commit()
    scanned = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/scan",
        headers=fixture["employee_headers"],
        json={"scanned_value": outside_asset.asset_code},
    )
    assert scanned.get_json()["data"]["outcome"] == "OUTSIDE_SCOPE"
    event = db.session.query(InventoryScanEvent).filter_by(task_id=task["id"]).one()
    resolved = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/scan-events/{event.id}/resolve",
        headers=fixture["admin_headers"],
        json={"resolution": "SURPLUS", "reason": "现场确认存在但不在任务快照中"},
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["resolution"] == "SURPLUS"

    reminded = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/reminders",
        headers=fixture["admin_headers"],
        json={"recipient_user_ids": [fixture["employee"].id]},
    )
    assert reminded.status_code == 200
    assert reminded.get_json()["data"]["recipient_count"] == 1
    reminder = db.session.query(InventoryReminder).filter_by(task_id=task["id"]).one()
    assert reminder.channel == "LOCAL_FEISHU"
    assert reminder.status == "QUEUED"

    report = client.get(
        f"/api/v1/inventory/tasks/{task['id']}/report",
        headers=fixture["admin_headers"],
    )
    assert report.status_code == 200
    assert report.mimetype == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    with ZipFile(BytesIO(report.data)) as workbook:
        names = workbook.namelist()
        assert "xl/workbook.xml" in names
        assert (
            len([name for name in names if name.startswith("xl/worksheets/sheet")]) == 9
        )
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
        assert "盘点汇总" in workbook_xml
        assert "人员完成情况" in workbook_xml


def test_task_filters_and_parent_child_suite_progress_are_snapshotted(client) -> None:
    fixture = _inventory_fixture(client)
    child = Asset(
        asset_code="INV-ASSET-CHILD",
        asset_name="MacBook 电源适配器",
        status=AssetStatus.IN_USE.value,
        organization_id=fixture["organization"].id,
        holder_user_id=fixture["employee"].id,
        usage_department_id=fixture["organization"].id,
        parent_asset_id=fixture["asset"].id,
        category_id=fixture["category"].id,
        unit_id=fixture["unit"].id,
        original_amount=Decimal("499.00"),
        purchase_date=date(2026, 7, 1),
        service_life_months=36,
        expected_expiry_date=date(2029, 7, 1),
        manager_id=fixture["admin"].id,
        source_id=fixture["source"].id,
        location_id=fixture["location"].id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
        normalized_serial="inventory-asset-sn-child",
        serial_number="INVENTORY-ASSET-SN-CHILD",
    )
    excluded = Asset(
        asset_code="INV-ASSET-IDLE-OTHER-MANAGER",
        asset_name="筛选外闲置资产",
        status=AssetStatus.IDLE.value,
        organization_id=fixture["organization"].id,
        holder_user_id=fixture["employee"].id,
        usage_department_id=fixture["organization"].id,
        category_id=fixture["category"].id,
        unit_id=fixture["unit"].id,
        original_amount=Decimal("999.00"),
        purchase_date=date(2026, 7, 4),
        service_life_months=36,
        expected_expiry_date=date(2029, 7, 4),
        manager_id=fixture["employee"].id,
        source_id=fixture["source"].id,
        location_id=fixture["location"].id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
        normalized_serial="inventory-asset-sn-filtered",
        serial_number="INVENTORY-ASSET-SN-FILTERED",
    )
    db.session.add_all([child, excluded])
    db.session.commit()

    response = client.post(
        "/api/v1/inventory/tasks",
        headers=fixture["admin_headers"],
        json={
            "name": "主附资产与范围筛选盘点",
            "deadline_at": "2030-01-01T00:00:00+00:00",
            "admin_user_ids": [fixture["admin"].id],
            "organization_ids": [fixture["organization"].id],
            "location_ids": [],
            "category_ids": [],
            "holder_user_ids": [],
            "manager_user_ids": [fixture["admin"].id],
            "asset_statuses": [AssetStatus.IN_USE.value],
            "public_responsible_user_id": fixture["employee"].id,
            "photo_source_mode": "CAMERA_OR_ALBUM",
            "min_photo_count": 1,
            "publish": True,
        },
    )
    assert response.status_code == 200
    task = response.get_json()["data"]
    assert task["counts"]["total"] == 2
    assert task["scope_filters"]["manager_user_ids"] == [fixture["admin"].id]
    assert task["scope_filters"]["asset_statuses"] == [AssetStatus.IN_USE.value]

    items = _task_items(client, task["id"], fixture["admin_headers"])
    assert {item["asset_code"] for item in items} == {
        fixture["asset"].asset_code,
        child.asset_code,
    }
    assert all(item["suite_progress"] == {"total": 2, "checked": 0} for item in items)
    child_item = next(item for item in items if item["asset_code"] == child.asset_code)
    assert child_item["parent_asset_code"] == fixture["asset"].asset_code

    parent_item = next(
        item for item in items if item["asset_code"] == fixture["asset"].asset_code
    )
    marked = client.post(
        f"/api/v1/inventory/tasks/{task['id']}/admin-mark",
        headers=fixture["admin_headers"],
        json={
            "item_ids": [parent_item["id"]],
            "reason": "主资产标签磨损，现场人工确认",
        },
    )
    assert marked.status_code == 200
    refreshed = _task_items(client, task["id"], fixture["admin_headers"])
    assert all(
        item["suite_progress"] == {"total": 2, "checked": 1} for item in refreshed
    )


def test_my_pending_items_endpoint_returns_empty_list_without_tasks(client) -> None:
    fixture = _inventory_fixture(client)

    response = client.get(
        "/api/v1/inventory/my-pending-items",
        headers=fixture["employee_headers"],
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == []


def test_my_pending_items_endpoint_returns_current_employee_assets(client) -> None:
    fixture = _inventory_fixture(client)
    _create_task(client, fixture)

    response = client.get(
        "/api/v1/inventory/my-pending-items",
        headers=fixture["employee_headers"],
    )

    assert response.status_code == 200
    items = response.get_json()["data"]
    assert len(items) == 1
    assert all(item["responsible_user_id"] == fixture["employee"].id for item in items)
    assert {item["asset_code"] for item in items} == {fixture["asset"].asset_code}
