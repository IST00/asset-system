from __future__ import annotations

from datetime import datetime, timezone

from app.enums import AssetStatus, DataScope, InventoryItemStatus
from app.extensions import db
from app.models import InventoryItem, InventoryTask, PublicUsageObject
from tests.test_assets import _asset_fixture, _copy_asset, _reader


def test_scan_intent_recommends_idle_personal_scenarios(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "scan-intent-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )

    response = client.get(
        "/api/v1/assets/scan-intent",
        headers=headers,
        query_string={"asset_code": asset.asset_code},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["id"] == asset.id
    assert data["scenarios"] == ["PERSONAL_USE", "PERSONAL_BORROW"]
    assert data["inventory_task"] is None


def test_scan_intent_adds_public_scenarios_for_usage_manager(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "scan-intent-manager",
        DataScope.ALL.value,
        ["asset:view", "asset:usage:manage"],
    )

    response = client.get(
        "/api/v1/assets/scan-intent",
        headers=headers,
        query_string={"asset_code": asset.asset_code},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["scenarios"] == [
        "PERSONAL_USE",
        "PERSONAL_BORROW",
        "PUBLIC_USE",
        "PUBLIC_BORROW",
    ]


def test_scan_intent_recommends_personal_return_for_holder(client) -> None:
    _organization, _other, manager, asset = _asset_fixture()
    holder, headers = _reader(
        client,
        "scan-intent-holder",
        DataScope.SELF.value,
        ["asset:view"],
        _organization,
    )
    asset.status = AssetStatus.IN_USE.value
    asset.usage_type = "PERSONAL"
    asset.holder_user_id = holder.id
    db.session.commit()

    response = client.get(
        "/api/v1/assets/scan-intent",
        headers=headers,
        query_string={"asset_code": asset.asset_code},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["scenarios"] == ["PERSONAL_RETURN"]
    assert data["holder_user_id"] == holder.id


def test_scan_intent_recommends_public_return_for_usage_manager(client) -> None:
    organization, _other, manager, asset = _asset_fixture()
    public_object = PublicUsageObject(code="SCAN-PUBLIC", name="会议室")
    db.session.add(public_object)
    db.session.flush()
    asset.status = AssetStatus.IN_USE.value
    asset.usage_type = "PUBLIC"
    asset.public_object_id = public_object.id
    db.session.commit()
    _user, headers = _reader(
        client,
        "scan-public-manager",
        DataScope.ALL.value,
        ["asset:view", "asset:usage:manage"],
    )

    response = client.get(
        "/api/v1/assets/scan-intent",
        headers=headers,
        query_string={"asset_code": asset.asset_code},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["scenarios"] == ["PUBLIC_RETURN"]
    assert data["public_object_name"] == "会议室"


def test_scan_intent_includes_active_inventory_task(client) -> None:
    organization, _other, manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "scan-inventory-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )
    task = InventoryTask(
        task_no="SCAN-INTENT-INV",
        name="季度盘点",
        status="IN_PROGRESS",
        deadline_at=datetime(2026, 12, 31, 15, 59, tzinfo=timezone.utc),
        created_by=manager.id,
        scope_filters={"organization_ids": [organization.id]},
    )
    db.session.add(task)
    db.session.flush()
    db.session.add(
        InventoryItem(
            task_id=task.id,
            asset_id=asset.id,
            responsible_user_id=_user.id,
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_status_snapshot=asset.status,
            organization_id=organization.id,
            organization_name=organization.name,
            category_id=asset.category_id,
            category_name="电脑",
            ledger_location_id=asset.location_id,
            ledger_location_name="仓库",
        )
    )
    db.session.commit()

    response = client.get(
        "/api/v1/assets/scan-intent",
        headers=headers,
        query_string={"asset_code": asset.asset_code},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["inventory_task"] == {
        "task_id": task.id,
        "task_no": "SCAN-INTENT-INV",
        "task_name": "季度盘点",
        "item_status": InventoryItemStatus.PENDING.value,
        "pending": True,
    }


def test_scan_intent_recommends_return_only_for_actual_holder(client) -> None:
    organization, _other, manager, asset = _asset_fixture()
    holder, holder_headers = _reader(
        client,
        "actual-holder",
        DataScope.SELF.value,
        ["asset:view"],
        organization,
    )
    copied = _copy_asset(
        asset,
        asset_code="SCAN-INTENT-OTHER",
        organization_id=organization.id,
        manager_id=manager.id,
        holder_user_id=holder.id,
    )
    copied.status = AssetStatus.IN_USE.value
    copied.usage_type = "PERSONAL"
    db.session.commit()

    response = client.get(
        "/api/v1/assets/scan-intent",
        headers=holder_headers,
        query_string={"asset_code": copied.asset_code},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["scenarios"] == ["PERSONAL_RETURN"]


def test_scan_intent_adds_public_scenarios_for_self_usage_employee(client) -> None:
    organization, _other, _manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "scan-intent-self-usage",
        DataScope.ALL.value,
        ["asset:view", "asset:usage:self"],
        organization,
    )

    response = client.get(
        "/api/v1/assets/scan-intent",
        headers=headers,
        query_string={"asset_code": asset.asset_code},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["scenarios"] == [
        "PERSONAL_USE",
        "PERSONAL_BORROW",
        "PUBLIC_USE",
        "PUBLIC_BORROW",
    ]
