from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.enums import DataScope, FlowStatus, OperationType, RecordStatus, SignMode
from app.extensions import db
from app.models import (
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
    ApprovalTask,
    AssetCategory,
    AssetCodeReservation,
    AssetCodeSequence,
    AssetLocation,
    AssetSource,
    OperationRequest,
    Organization,
    Permission,
    Role,
    RolePermission,
    StockInItem,
    StockInRequest,
    Supplier,
    Unit,
    User,
    UserRole,
)
from app.security.passwords import hash_password
from app.schemas.stock_in import CreateStockInRequestSchema, StockInItemRequestSchema
from app.services import stock_in_service
from config import TestConfig


def _role_with_permissions(code: str, *permission_codes: str) -> Role:
    role = Role(code=code, name=code, data_scope=DataScope.ALL.value)
    permissions = [
        Permission(code=item, name=item, module=item.split(":")[0])
        for item in permission_codes
    ]
    db.session.add_all([role, *permissions])
    db.session.flush()
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    return role


def _assign(user: User, role: Role) -> None:
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))


def _setup(client, with_approver: bool = True):
    organization = Organization(code="358466", name="公司")
    unit = Unit(code="UNIT", name="台")
    source = AssetSource(code="PURCHASE", name="采购")
    location = AssetLocation(code="LOC000001", name="仓库", is_selectable=True)
    applicant = User(
        username="stock-applicant", password=hash_password("admin123"), enabled=True
    )
    manager = User(username="asset-manager", password="x", enabled=True)
    create_role = _role_with_permissions(
        "STOCK_CREATOR", "stock-in:create", "stock-in:view"
    )
    db.session.add_all([organization, unit, source, location, applicant, manager])
    db.session.flush()
    _assign(applicant, create_role)
    category = AssetCategory(
        code="10100", name="笔记本电脑", service_life_months=36, default_unit_id=unit.id
    )
    db.session.add(category)
    approver = None
    if with_approver:
        approver = User(username="stock-approver", password="x", enabled=True)
        approve_role = _role_with_permissions("STOCK_APPROVER", "stock-in:approve")
        db.session.add(approver)
        db.session.flush()
        _assign(approver, approve_role)
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "stock-applicant", "password": "admin123"},
    ).get_json()["data"]["token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "organization": organization,
        "unit": unit,
        "source": source,
        "location": location,
        "applicant": applicant,
        "manager": manager,
        "category": category,
        "approver": approver,
    }


def _item(context, **overrides):
    item = {
        "asset_name": "MacBook Air",
        "category_id": context["category"].id,
        "unit_id": context["unit"].id,
        "original_amount": "7999.00",
        "purchase_date": date(2026, 7, 17).isoformat(),
        "manager_id": context["manager"].id,
        "source_id": context["source"].id,
        "location_id": context["location"].id,
        "serial_number": " SN-001 ",
    }
    item.update(overrides)
    return item


def _schema_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "asset_name": "MacBook Air",
        "category_id": 1,
        "unit_id": 2,
        "original_amount": "7999.00",
        "purchase_date": date(2026, 7, 17).isoformat(),
        "manager_id": 3,
        "source_id": 4,
        "location_id": 5,
    }
    item.update(overrides)
    return item


def test_stock_in_item_schema_accepts_frozen_fields_and_nested_json() -> None:
    custom_attributes = {
        "warranty": {"years": 3, "onsite": True},
        "tags": ["laptop", None, 2026],
    }

    loaded = StockInItemRequestSchema().load(
        _schema_item(
            service_life_months=48,
            supplier_id=None,
            custom_attributes=custom_attributes,
        )
    )

    assert loaded["service_life_months"] == 48
    assert loaded["supplier_id"] is None
    assert loaded["custom_attributes"] == custom_attributes


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("service_life_months", "48"),
        ("service_life_months", True),
        ("supplier_id", "1"),
        ("supplier_id", True),
    ],
)
def test_stock_in_item_schema_uses_strict_integers(field: str, value: object) -> None:
    with pytest.raises(ValidationError) as error:
        StockInItemRequestSchema().load(_schema_item(**{field: value}))

    assert error.value.messages[field] == ["Not a valid integer."]


@pytest.mark.parametrize("service_life_months", [0, 1201])
def test_stock_in_item_schema_limits_service_life(
    service_life_months: int,
) -> None:
    with pytest.raises(ValidationError) as error:
        StockInItemRequestSchema().load(
            _schema_item(service_life_months=service_life_months)
        )

    assert error.value.messages["service_life_months"] == [
        "Must be greater than or equal to 1 and less than or equal to 1200."
    ]


@pytest.mark.parametrize(
    "custom_attributes",
    [
        {"value": float("nan")},
        {"value": float("inf")},
        {"nested": {"value": {1, 2}}},
        {"nested": {"value": object()}},
    ],
    ids=["nan", "infinity", "nested-set", "nested-object"],
)
def test_stock_in_item_schema_rejects_non_json_custom_attributes(
    custom_attributes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError) as error:
        StockInItemRequestSchema().load(
            _schema_item(custom_attributes=custom_attributes)
        )

    assert error.value.messages["custom_attributes"] == ["自定义属性必须是合法JSON"]


def test_stock_in_item_schema_enforces_compact_json_utf8_limit() -> None:
    compact_overhead = len(
        json.dumps(
            {"x": ""},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    value_byte_limit = 16 * 1024 - compact_overhead
    multibyte_character = "资"
    character_bytes = len(multibyte_character.encode("utf-8"))
    character_count, ascii_remainder = divmod(value_byte_limit, character_bytes)
    at_limit = multibyte_character * character_count + "a" * ascii_remainder
    assert len(at_limit.encode("utf-8")) == value_byte_limit

    loaded = StockInItemRequestSchema().load(
        _schema_item(custom_attributes={"x": at_limit})
    )
    assert loaded["custom_attributes"] == {"x": at_limit}

    with pytest.raises(ValidationError) as error:
        StockInItemRequestSchema().load(
            _schema_item(custom_attributes={"x": f"{at_limit}a"})
        )
    assert error.value.messages["custom_attributes"] == ["自定义属性不能超过16KB"]


@pytest.mark.parametrize("key", ["", "x" * 129])
def test_stock_in_item_schema_limits_custom_attribute_keys(key: str) -> None:
    with pytest.raises(ValidationError) as error:
        StockInItemRequestSchema().load(_schema_item(custom_attributes={key: 1}))

    assert "custom_attributes" in error.value.messages


@pytest.mark.parametrize("field", ["unit_id", "source_id", "location_id"])
def test_stock_in_item_schema_keeps_foundation_fields_required(field: str) -> None:
    payload = _schema_item()
    payload.pop(field)

    with pytest.raises(ValidationError) as error:
        StockInItemRequestSchema().load(payload)

    assert field in error.value.messages


@pytest.mark.parametrize("field", ["unit_id", "source_id", "location_id"])
@pytest.mark.parametrize("value", ["1", True, 1.0])
def test_stock_in_item_schema_keeps_foundation_fields_strict(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError) as error:
        StockInItemRequestSchema().load(_schema_item(**{field: value}))

    assert error.value.messages[field] == ["Not a valid integer."]


def test_item_validation_deep_copies_nested_custom_attributes(client) -> None:
    context = _setup(client)
    loaded = StockInItemRequestSchema().load(
        _item(
            context,
            serial_number="VALIDATION-COPY",
            custom_attributes={"nested": {"value": 1}},
        )
    )

    validated = stock_in_service._validate_item(loaded, set())
    validated["custom_attributes"]["nested"]["value"] = 2

    assert loaded["custom_attributes"] == {"nested": {"value": 1}}


def test_submit_reserves_codes_and_snapshots_approvers(client) -> None:
    context = _setup(client)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "remark": "首批入库",
            "items": [
                _item(context),
                _item(context, asset_name="MacBook Pro", serial_number="SN-002"),
            ],
        },
    )
    body = response.get_json()

    assert body["code"] == 200
    assert body["data"]["approval_status"] == "PENDING"
    assert body["data"]["execution_status"] == "NOT_STARTED"
    assert [item["asset_code"] for item in body["data"]["items"]] == [
        "358466-10100-0001",
        "358466-10100-0002",
    ]
    assert db.session.query(AssetCodeReservation).count() == 2
    assert db.session.query(ApprovalTask).one().approver_id == context["approver"].id


def test_submit_without_service_life_uses_category_default(client) -> None:
    context = _setup(client)

    body = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context, serial_number="DEFAULT-LIFE")],
        },
    ).get_json()

    assert body["code"] == 200
    item = body["data"]["items"][0]
    assert item["supplier_id"] is None
    assert item["supplier_snapshot"] is None
    assert item["service_life_months"] == 36
    assert item["expected_expiry_date"] == "2029-07-17"
    assert item["custom_attributes"] == {}


def test_item_serialization_deep_copies_nested_custom_attributes(client) -> None:
    context = _setup(client)
    body = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [
                _item(
                    context,
                    serial_number="SERIALIZATION-COPY",
                    custom_attributes={"nested": {"value": 1}},
                )
            ],
        },
    ).get_json()
    assert body["code"] == 200
    item = db.session.query(StockInItem).one()

    serialized = stock_in_service._serialize_item(item, include_amount=False)
    serialized["custom_attributes"]["nested"]["value"] = 2

    assert item.custom_attributes == {"nested": {"value": 1}}


def test_explicit_service_life_requires_permission_before_business_writes(
    client,
) -> None:
    context = _setup(client)

    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [
                _item(
                    context,
                    serial_number="LIFE-NO-PERMISSION",
                    service_life_months=48,
                )
            ],
        },
    )
    body = response.get_json()

    assert body["code"] == 403
    assert body["message"] == "无操作权限"
    assert db.session.query(ApprovalFlowDefinition).count() == 0
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(StockInRequest).count() == 0
    assert db.session.query(StockInItem).count() == 0
    assert db.session.query(AssetCodeSequence).count() == 0
    assert db.session.query(AssetCodeReservation).count() == 0


def test_disabled_supplier_is_rejected_before_business_writes(client) -> None:
    context = _setup(client)
    supplier = Supplier(
        code="SUP-DISABLED",
        name="停用供应商",
        status=RecordStatus.DISABLED.value,
    )
    db.session.add(supplier)
    db.session.commit()

    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [
                _item(
                    context,
                    serial_number="DISABLED-SUPPLIER",
                    supplier_id=supplier.id,
                )
            ],
        },
    )
    body = response.get_json()

    assert body["code"] == 1000
    assert body["message"] == "供应商不存在或已停用"
    assert db.session.query(ApprovalFlowDefinition).count() == 0
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(StockInRequest).count() == 0
    assert db.session.query(StockInItem).count() == 0
    assert db.session.query(AssetCodeSequence).count() == 0
    assert db.session.query(AssetCodeReservation).count() == 0


def test_missing_supplier_is_rejected_before_business_writes(client) -> None:
    context = _setup(client)

    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [
                _item(
                    context,
                    serial_number="MISSING-SUPPLIER",
                    supplier_id=999_999,
                )
            ],
        },
    )
    body = response.get_json()

    assert body["code"] == 1000
    assert body["message"] == "供应商不存在"
    assert db.session.query(ApprovalFlowDefinition).count() == 0
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(StockInRequest).count() == 0
    assert db.session.query(StockInItem).count() == 0
    assert db.session.query(AssetCodeSequence).count() == 0
    assert db.session.query(AssetCodeReservation).count() == 0


def test_submit_replays_same_idempotency_key_without_new_business_rows(client) -> None:
    context = _setup(client)
    payload = {
        "organization_id": context["organization"].id,
        "idempotency_key": "stock-in-once",
        "items": [_item(context, serial_number="IDEMPOTENT-STOCK")],
    }

    first = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json=payload,
    ).get_json()
    replayed = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json=payload,
    ).get_json()

    assert first["code"] == 200
    assert replayed["code"] == 200
    assert replayed["data"]["id"] == first["data"]["id"]
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(StockInItem).count() == 1
    assert db.session.query(ApprovalTask).count() == 1
    assert db.session.query(AssetCodeReservation).count() == 1


def test_concurrent_stock_in_submit_replays_one_request(tmp_path) -> None:
    database = tmp_path / "stock-in-idempotency-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        context = _setup(concurrent_app.test_client())
        stock_in_service._stock_in_flow([context["approver"].id])
        db.session.commit()
        actor_id = context["applicant"].id
        payload = CreateStockInRequestSchema().load(
            {
                "organization_id": context["organization"].id,
                "idempotency_key": "concurrent-stock-in",
                "items": [_item(context, serial_number="CONCURRENT-STOCK")],
            }
        )

    barrier = Barrier(2)

    def submit() -> int:
        with concurrent_app.app_context():
            barrier.wait()
            result = stock_in_service.submit(payload, actor_id)
            return int(result["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: submit(), range(2)))

    assert operation_ids[0] == operation_ids[1]
    with concurrent_app.app_context():
        assert db.session.query(OperationRequest).count() == 1
        assert db.session.query(StockInItem).count() == 1
        assert db.session.query(ApprovalTask).count() == 1
        assert db.session.query(AssetCodeReservation).count() == 1
        db.drop_all()


def test_submit_without_approver_creates_nothing(client) -> None:
    context = _setup(client, with_approver=False)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    )

    assert response.get_json()["code"] == 1000
    assert "审批人" in response.get_json()["message"]
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(AssetCodeSequence).count() == 0


def test_invalid_published_flow_rolls_back_all_submission_writes(client) -> None:
    context = _setup(client)
    definition = ApprovalFlowDefinition(
        operation_type=OperationType.STOCK_IN.value,
        name="无有效审批人入库流",
        status=FlowStatus.PUBLISHED.value,
    )
    db.session.add(definition)
    db.session.flush()
    version = ApprovalFlowVersion(
        flow_definition_id=definition.id,
        version_no=1,
        status=FlowStatus.PUBLISHED.value,
    )
    db.session.add(version)
    db.session.flush()
    db.session.add(
        ApprovalFlowLayer(
            flow_version_id=version.id,
            level_no=1,
            sign_mode=SignMode.OR_SIGN.value,
            allow_self_approval=False,
        )
    )
    db.session.commit()

    body = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [
                _item(
                    context,
                    serial_number="INVALID-FLOW-ROLLBACK",
                )
            ],
        },
    ).get_json()

    assert body["code"] == 1000
    assert body["message"] == "审批第 1 层没有有效审批人"
    db.session.commit()
    db.session.remove()
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(StockInRequest).count() == 0
    assert db.session.query(StockInItem).count() == 0
    assert db.session.query(AssetCodeSequence).count() == 0
    assert db.session.query(AssetCodeReservation).count() == 0


def test_non_testing_submit_requires_prepublished_stock_in_flow(app, client) -> None:
    context = _setup(client)
    app.config["TESTING"] = False

    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context, serial_number="NO-DYNAMIC-FLOW")],
        },
    ).get_json()

    assert response["code"] == 1000
    assert "审批流尚未发布" in response["message"]
    assert db.session.query(ApprovalFlowDefinition).count() == 0


def test_zero_amount_requires_reason_and_batch_validation_is_atomic(client) -> None:
    context = _setup(client)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [
                _item(context, serial_number="VALID"),
                _item(context, original_amount="0.00", serial_number="ZERO"),
            ],
        },
    )

    assert response.status_code == 400
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(StockInItem).count() == 0


def test_pending_serial_number_is_unique_ignoring_case_and_spaces(client) -> None:
    context = _setup(client)
    first = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={"organization_id": context["organization"].id, "items": [_item(context)]},
    )
    assert first.get_json()["code"] == 200

    duplicate = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context, serial_number="sn-001")],
        },
    )
    assert duplicate.get_json()["code"] == 1000
    assert "序列号" in duplicate.get_json()["message"]


def test_serial_reservation_conflict_is_a_safe_business_error(
    client, monkeypatch
) -> None:
    context = _setup(client)
    from app.repositories.workflow_repository import stock_in_item_repository

    def conflict(_item):
        raise IntegrityError(
            "INSERT INTO stock_in_items (...) VALUES (...) ",
            {},
            Exception(
                "UNIQUE constraint failed: stock_in_items.serial_reservation_key"
            ),
        )

    monkeypatch.setattr(stock_in_item_repository, "add", conflict)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["code"] == 1000
    assert body["message"] == "设备序列号已被其他申请占用"
    assert "UNIQUE" not in body["message"]


def test_rejected_request_releases_serial_reservation(client) -> None:
    context = _setup(client)
    first = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()["data"]

    stock_in_service.reject(first["id"], "资料不完整", context["approver"].id)

    replacement = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()
    assert replacement["code"] == 200
    assert replacement["data"]["items"][0]["asset_code"].endswith("-0002")


def test_stock_in_list_is_paginated_filtered_and_newest_first(client) -> None:
    context = _setup(client)
    submitted = []
    for index in range(2):
        response = client.post(
            "/api/v1/stock-in-requests",
            headers=context["headers"],
            json={
                "organization_id": context["organization"].id,
                "items": [_item(context, serial_number=f"LIST-{index}")],
            },
        )
        submitted.append(response.get_json()["data"])

    response = client.get(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        query_string={"page": 0, "size": 1, "approval_status": "PENDING"},
    )
    body = response.get_json()

    assert body["code"] == 200
    assert body["data"]["total"] == 2
    assert body["data"]["page"] == 0
    assert body["data"]["size"] == 1
    item = body["data"]["items"][0]
    assert item["id"] == submitted[1]["id"]
    assert item["request_no"] == submitted[1]["request_no"]
    assert item["organization_id"] == context["organization"].id
    assert item["applicant_id"] == context["applicant"].id
    assert item["approval_status"] == "PENDING"
    assert item["execution_status"] == "NOT_STARTED"
    assert item["created_at"]

    filtered = client.get(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        query_string={"request_no": submitted[0]["request_no"]},
    ).get_json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == submitted[0]["id"]


def test_stock_in_list_applies_organization_scope_in_query(client) -> None:
    context = _setup(client)
    submitted = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context, serial_number="SCOPED-LIST")],
        },
    ).get_json()["data"]
    other_organization = Organization(code="OTHER", name="其他组织")
    reader = User(
        username="scoped-stock-reader",
        password=hash_password("admin123"),
        enabled=True,
    )
    role = Role(
        code="SCOPED_STOCK_READER",
        name="SCOPED_STOCK_READER",
        data_scope=DataScope.DEPARTMENT.value,
    )
    db.session.add_all([other_organization, reader])
    db.session.add(role)
    db.session.flush()
    reader.organization_id = other_organization.id
    _assign(reader, role)
    view_permission = db.session.query(Permission).filter_by(code="stock-in:view").one()
    db.session.add(RolePermission(role_id=role.id, permission_id=view_permission.id))
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": reader.username, "password": "admin123"},
    ).get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    hidden = client.get("/api/v1/stock-in-requests", headers=headers).get_json()["data"]
    assert hidden["total"] == 0

    reader.organization_id = context["organization"].id
    db.session.commit()
    visible = client.get("/api/v1/stock-in-requests", headers=headers).get_json()[
        "data"
    ]
    assert visible["total"] == 1
    assert visible["items"][0]["id"] == submitted["id"]


def test_stock_in_detail_hides_amount_without_field_permission(client) -> None:
    context = _setup(client)
    submitted = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()["data"]

    hidden = client.get(
        f"/api/v1/stock-in-requests/{submitted['id']}",
        headers=context["headers"],
    ).get_json()["data"]["items"][0]
    assert "original_amount" not in hidden
    assert "zero_amount_reason" not in hidden

    amount_permission = Permission(
        code="asset:amount:view", name="查看资产金额", module="asset"
    )
    role_id = (
        db.session.query(UserRole)
        .filter_by(user_id=context["applicant"].id)
        .one()
        .role_id
    )
    db.session.add(amount_permission)
    db.session.flush()
    db.session.add(RolePermission(role_id=role_id, permission_id=amount_permission.id))
    db.session.commit()

    visible = client.get(
        f"/api/v1/stock-in-requests/{submitted['id']}",
        headers=context["headers"],
    ).get_json()["data"]["items"][0]
    assert visible["original_amount"] == "7999.00"
    assert visible["zero_amount_reason"] is None


def test_self_scope_consistently_allows_own_list_detail_and_withdraw(client) -> None:
    context = _setup(client)
    submitted = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()["data"]
    role_id = (
        db.session.query(UserRole)
        .filter_by(user_id=context["applicant"].id)
        .one()
        .role_id
    )
    role = db.session.get(Role, role_id)
    assert role is not None
    role.data_scope = DataScope.SELF.value
    db.session.commit()

    listed = client.get(
        "/api/v1/stock-in-requests", headers=context["headers"]
    ).get_json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == submitted["id"]

    detail = client.get(
        f"/api/v1/stock-in-requests/{submitted['id']}",
        headers=context["headers"],
    ).get_json()
    assert detail["code"] == 200
    assert detail["data"]["id"] == submitted["id"]

    withdrawn = client.post(
        f"/api/v1/stock-in-requests/{submitted['id']}/withdraw",
        headers=context["headers"],
        json={"reason": "申请内容需要调整"},
    ).get_json()
    assert withdrawn["code"] == 200
    assert withdrawn["data"]["approval_status"] == "WITHDRAWN"
