from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import inspect
import json
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalStatus,
    AssetDataCompleteness,
    AssetStatus,
    DataScope,
    ExecutionStatus,
    OperationType,
    RecordStatus,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    OperationLog,
    OperationRequest,
    Organization,
    Permission,
    Role,
    RolePermission,
    StockInItem,
    StockInRequest,
    Supplier,
    SupplierCodeSequence,
    Unit,
    User,
    UserRole,
)
from app.repositories.asset_repository import asset_repository
from app.repositories.supplier_repository import (
    SupplierCodeSequenceRepository,
    SupplierRepository,
    supplier_code_sequence_repository,
    supplier_repository,
)
from app.repositories.workflow_repository import stock_in_item_repository
from app.security.passwords import hash_password
from app.services import audit_service, permission_service, supplier_service
from config import TestConfig


SUPPLIER_PERMISSIONS = (
    "supplier:view",
    "supplier:create",
    "supplier:edit",
    "supplier:disable",
    "supplier:delete",
)


def _grant_actor(
    username: str = "supplier-actor",
    permission_codes: tuple[str, ...] = SUPPLIER_PERMISSIONS,
) -> int:
    actor = User(username=username, password="x", enabled=True)
    role = Role(
        code=f"{username.upper()}_ROLE",
        name=username,
        data_scope=DataScope.ALL.value,
    )
    permissions = [
        Permission(code=code, name=code, module="supplier") for code in permission_codes
    ]
    db.session.add_all([actor, role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=role.id))
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id)
            for permission in permissions
        ]
    )
    db.session.commit()
    return actor.id


def _payload(
    name: str,
    credit: str | None,
    *,
    phone: str = "13812345678",
) -> dict[str, Any]:
    return {
        "name": name,
        "unified_social_credit_code": credit,
        "contact_name": "张三",
        "contact_phone": phone,
        "address": "秘密地址",
        "remark": "秘密备注",
    }


def _create_supplier(
    actor_id: int,
    name: str = "甲供应商",
    credit: str | None = "credit-001",
) -> dict[str, Any]:
    return supplier_service.create_supplier(_payload(name, credit), actor_id)


def _supplier_http_headers(
    client,
    *,
    username: str = "supplier-http-actor",
    permission_codes: tuple[str, ...] = SUPPLIER_PERMISSIONS,
) -> dict[str, str]:
    actor = User(
        username=username,
        password=hash_password("admin123"),
        enabled=True,
    )
    role = Role(
        code=f"{username.upper()}_ROLE",
        name=username,
        data_scope=DataScope.ALL.value,
    )
    permissions = [
        Permission(code=code, name=code, module="supplier") for code in permission_codes
    ]
    db.session.add_all([actor, role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=role.id))
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id)
            for permission in permissions
        ]
    )
    db.session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "admin123"},
    )
    assert login.status_code == 200
    token = login.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _concurrent_app(tmp_path: Path, database_name: str) -> Flask:
    database = tmp_path / database_name

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    return create_app(config=ConcurrentConfig)


def test_repository_queries_are_exact_ordered_and_cas_fields_are_restricted(
    app,
) -> None:
    repository = SupplierRepository()
    first = repository.add(
        Supplier(
            code="SUP000002",
            name="甲供应商扩展",
            unified_social_credit_code="CREDIT-2",
        )
    )
    second = repository.add(
        Supplier(
            code="SUP000001",
            name="甲供应商",
            unified_social_credit_code="CREDIT-1",
        )
    )

    assert repository.find_by_code("SUP000001") is second
    assert repository.find_by_name("甲供应") is None
    assert repository.find_by_name("甲供应商") is second
    assert repository.find_by_credit_code("credit-1") is None
    assert repository.find_by_credit_code("CREDIT-1") is second
    assert repository.find_for_update(first.id) is first
    assert [item.code for item in repository.list_all()] == [
        "SUP000001",
        "SUP000002",
    ]

    assert repository.cas_update(second.id, 1, {"remark": "changed"}) is True
    db.session.expire_all()
    assert db.session.get(Supplier, second.id).version == 2
    with pytest.raises(BusinessException):
        repository.cas_update(second.id, 2, {})
    with pytest.raises(BusinessException):
        repository.cas_update(second.id, 2, {"code": "forbidden"})


def test_sequence_repository_uses_sup_prefix_and_allocate_is_monotonic_after_delete(
    app,
) -> None:
    sequence_repository = SupplierCodeSequenceRepository()
    assert list(inspect.signature(sequence_repository.ensure_exists).parameters) == []
    assert list(inspect.signature(sequence_repository.find_for_update).parameters) == []
    sequence_repository.ensure_exists()
    sequence_repository.ensure_exists()
    sequence = sequence_repository.find_for_update()
    assert sequence is not None
    assert sequence.prefix == "SUP"
    assert db.session.query(SupplierCodeSequence).count() == 1

    actor_id = _grant_actor()
    first = _create_supplier(actor_id, "第一家", "credit-one")
    supplier_service.delete_supplier(
        first["id"], first["version"], actor_id, "  重复录入  "
    )
    second = _create_supplier(actor_id, "第二家", "credit-two")

    assert first["code"] == "SUP000001"
    assert second["code"] == "SUP000002"
    assert db.session.get(SupplierCodeSequence, "SUP").current_value == 2


def test_create_normalizes_unique_fields_and_requires_explicit_disabled_restore(
    app,
) -> None:
    actor_id = _grant_actor()
    created = supplier_service.create_supplier(
        _payload("  Acme Supplier  ", "  uscc-abc  "), actor_id
    )
    assert created["name"] == "Acme Supplier"
    assert created["unified_social_credit_code"] == "USCC-ABC"

    with pytest.raises(BusinessException, match="供应商已存在"):
        supplier_service.create_supplier(
            _payload("Acme Supplier", "USCC-OTHER"), actor_id
        )
    with pytest.raises(BusinessException, match="供应商已存在"):
        supplier_service.create_supplier(_payload("另一家", " uscc-abc "), actor_id)

    disabled = supplier_service.set_supplier_enabled(
        created["id"], False, created["version"], actor_id
    )
    before_logs = db.session.query(OperationLog).count()
    with pytest.raises(BusinessException, match="恢复启用"):
        supplier_service.create_supplier(
            _payload(" Acme Supplier ", " uscc-abc ", phone="12345"), actor_id
        )

    persisted = db.session.get(Supplier, created["id"])
    assert persisted is not None
    assert persisted.status == RecordStatus.DISABLED.value
    assert persisted.contact_phone == "13812345678"
    assert persisted.version == disabled["version"]
    assert db.session.query(Supplier).count() == 1
    assert db.session.get(SupplierCodeSequence, "SUP").current_value == 1
    assert db.session.query(OperationLog).count() == before_logs

    restored = supplier_service.set_supplier_enabled(
        created["id"], True, disabled["version"], actor_id
    )
    assert restored["status"] == RecordStatus.ENABLED.value
    assert restored["version"] == disabled["version"] + 1


def test_blank_name_and_blank_delete_reason_are_rejected(app) -> None:
    actor_id = _grant_actor()
    with pytest.raises(BusinessException) as blank_name:
        supplier_service.create_supplier(_payload("   ", None), actor_id)
    assert blank_name.value.code == ResultCode.BAD_REQUEST.code
    with pytest.raises(BusinessException) as null_name:
        supplier_service.create_supplier({"name": None}, actor_id)
    assert null_name.value.code == ResultCode.BAD_REQUEST.code
    created = _create_supplier(actor_id)
    with pytest.raises(BusinessException) as blank_reason:
        supplier_service.delete_supplier(
            created["id"], created["version"], actor_id, "   "
        )
    assert blank_reason.value.code == ResultCode.BAD_REQUEST.code
    with pytest.raises(BusinessException) as null_reason:
        supplier_service.delete_supplier(
            created["id"], created["version"], actor_id, None
        )
    assert null_reason.value.code == ResultCode.BAD_REQUEST.code
    assert db.session.get(Supplier, created["id"]) is not None


def test_public_signatures_accept_actor_id_keyword(app) -> None:
    actor_id = _grant_actor()
    created = supplier_service.create_supplier(
        _payload("关键字供应商", "keyword-credit"), actor_id=actor_id
    )
    assert supplier_service.list_suppliers(actor_id=actor_id)
    updated = supplier_service.update_supplier(
        created["id"],
        {"name": "关键字供应商二", "version": created["version"]},
        actor_id=actor_id,
    )
    disabled = supplier_service.set_supplier_enabled(
        created["id"], False, updated["version"], actor_id=actor_id
    )
    supplier_service.delete_supplier(
        created["id"],
        disabled["version"],
        actor_id=actor_id,
        reason="关键字删除",
    )


def test_public_use_cases_reject_an_actor_without_supplier_permissions(app) -> None:
    privileged_actor_id = _grant_actor("supplier-privileged")
    denied_actor_id = _grant_actor("supplier-denied", ())
    created = _create_supplier(privileged_actor_id)

    calls = (
        lambda: supplier_service.list_suppliers(denied_actor_id),
        lambda: supplier_service.create_supplier(
            _payload("无权创建", "denied-create"), denied_actor_id
        ),
        lambda: supplier_service.update_supplier(
            created["id"],
            {"name": "无权更新", "version": created["version"]},
            denied_actor_id,
        ),
        lambda: supplier_service.set_supplier_enabled(
            created["id"], False, created["version"], denied_actor_id
        ),
        lambda: supplier_service.delete_supplier(
            created["id"], created["version"], denied_actor_id, "无权删除"
        ),
    )
    for call in calls:
        with pytest.raises(BusinessException) as denied:
            call()
        assert denied.value.code == ResultCode.FORBIDDEN.code

    persisted = db.session.get(Supplier, created["id"])
    assert persisted is not None
    assert persisted.name == created["name"]
    assert persisted.status == RecordStatus.ENABLED.value
    assert persisted.version == created["version"]


def test_public_use_cases_require_the_exact_permission(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()
    required: list[tuple[int, str]] = []

    def record_permission(user_id: int, code: str) -> None:
        required.append((user_id, code))

    monkeypatch.setattr(permission_service, "require_permission", record_permission)
    created = _create_supplier(actor_id)
    supplier_service.list_suppliers(actor_id)
    updated = supplier_service.update_supplier(
        created["id"], {"name": "更新供应商", "version": created["version"]}, actor_id
    )
    disabled = supplier_service.set_supplier_enabled(
        created["id"], False, updated["version"], actor_id
    )
    supplier_service.delete_supplier(
        created["id"], disabled["version"], actor_id, "测试删除"
    )

    assert required == [
        (actor_id, "supplier:create"),
        (actor_id, "supplier:view"),
        (actor_id, "supplier:edit"),
        (actor_id, "supplier:disable"),
        (actor_id, "supplier:delete"),
    ]


def test_audit_actions_use_safe_dedicated_snapshots_and_delete_reason(app) -> None:
    actor_id = _grant_actor()
    created = _create_supplier(actor_id)
    updated = supplier_service.update_supplier(
        created["id"],
        {
            "name": "新名称",
            "contact_name": "李四",
            "contact_phone": "12345678",
            "address": "新秘密地址",
            "remark": "新秘密备注",
            "version": created["version"],
        },
        actor_id,
    )
    disabled = supplier_service.set_supplier_enabled(
        created["id"], False, updated["version"], actor_id
    )
    enabled = supplier_service.set_supplier_enabled(
        created["id"], True, disabled["version"], actor_id
    )
    supplier_service.delete_supplier(
        created["id"], enabled["version"], actor_id, "  合同终止  "
    )

    logs = db.session.query(OperationLog).order_by(OperationLog.id.asc()).all()
    assert [log.action for log in logs] == [
        "SUPPLIER_CREATE",
        "SUPPLIER_UPDATE",
        "SUPPLIER_DISABLE",
        "SUPPLIER_ENABLE",
        "SUPPLIER_DELETE",
    ]
    expected_keys = {
        "id",
        "code",
        "name",
        "unified_social_credit_code",
        "contact_phone",
        "status",
        "version",
    }
    for log in logs:
        assert log.resource_type == "supplier"
        assert log.resource_id == str(created["id"])
        assert log.operator_id == actor_id
        for snapshot in (log.before_data, log.after_data):
            if snapshot is not None:
                assert set(snapshot) == expected_keys
    serialized_logs = json.dumps(
        [log.before_data for log in logs] + [log.after_data for log in logs],
        ensure_ascii=False,
    )
    for secret in (
        "13812345678",
        "12345678",
        "张三",
        "李四",
        "秘密地址",
        "新秘密地址",
        "秘密备注",
        "新秘密备注",
    ):
        assert secret not in serialized_logs
    assert logs[0].before_data is None
    assert logs[0].after_data["contact_phone"] == "138****5678"
    assert logs[1].before_data is not None
    assert logs[1].after_data is not None
    assert logs[1].after_data["contact_phone"] == "********"
    assert logs[-1].after_data is None
    assert logs[-1].reason == "合同终止"


def test_each_successful_supplier_mutation_commits_exactly_once(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()
    original_commit = db.session.commit
    commit_count = 0

    def counting_commit() -> None:
        nonlocal commit_count
        commit_count += 1
        original_commit()

    monkeypatch.setattr(db.session, "commit", counting_commit)
    created = _create_supplier(actor_id)
    assert commit_count == 1
    updated = supplier_service.update_supplier(
        created["id"], {"name": "一次提交二", "version": created["version"]}, actor_id
    )
    assert commit_count == 2
    disabled = supplier_service.set_supplier_enabled(
        created["id"], False, updated["version"], actor_id
    )
    assert commit_count == 3
    enabled = supplier_service.set_supplier_enabled(
        created["id"], True, disabled["version"], actor_id
    )
    assert commit_count == 4
    supplier_service.delete_supplier(
        created["id"], enabled["version"], actor_id, "一次提交删除"
    )
    assert commit_count == 5


def test_record_resource_change_stages_without_committing(app) -> None:
    actor_id = _grant_actor()
    audit_service.record_resource_change(
        action="SUPPLIER_UPDATE",
        resource_type="supplier",
        resource_id="99",
        actor_id=actor_id,
        before_data={"version": 1},
        after_data={"version": 2},
    )
    db.session.rollback()
    assert db.session.query(OperationLog).count() == 0


def test_update_and_enable_use_cas_and_stale_work_rolls_back(app) -> None:
    actor_id = _grant_actor()
    created = _create_supplier(actor_id)
    supplier = db.session.get(Supplier, created["id"])
    supplier.remark = "must roll back"

    with pytest.raises(BusinessException):
        supplier_service.update_supplier(
            created["id"], {"name": "stale", "version": 0}, actor_id
        )
    db.session.expire_all()
    persisted = db.session.get(Supplier, created["id"])
    assert persisted.remark == "秘密备注"
    assert persisted.version == 1

    with pytest.raises(BusinessException):
        supplier_service.set_supplier_enabled(created["id"], False, 0, actor_id)
    db.session.expire_all()
    persisted = db.session.get(Supplier, created["id"])
    assert persisted.status == RecordStatus.ENABLED.value
    assert persisted.version == 1
    assert [log.action for log in db.session.query(OperationLog).all()] == [
        "SUPPLIER_CREATE"
    ]


def test_require_enabled_supplier_rejects_disabled_supplier(app) -> None:
    actor_id = _grant_actor()
    created = _create_supplier(actor_id)
    assert supplier_service.require_enabled_supplier(created["id"]).id == created["id"]
    supplier_service.set_supplier_enabled(
        created["id"], False, created["version"], actor_id
    )
    with pytest.raises(BusinessException):
        supplier_service.require_enabled_supplier(created["id"])


def _add_supplier_reference(supplier_id: int, reference_type: str) -> None:
    organization = Organization(code=f"ORG-{reference_type}", name="公司")
    unit = Unit(code=f"UNIT-{reference_type}", name="台")
    source = AssetSource(code=f"SOURCE-{reference_type}", name="采购")
    location = AssetLocation(
        code=f"LOC-{reference_type}", name="仓库", is_selectable=True
    )
    manager = User(username=f"manager-{reference_type}", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, manager])
    db.session.flush()
    category = AssetCategory(
        code=f"CATEGORY-{reference_type}",
        name=f"分类-{reference_type}",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    if reference_type == "asset":
        db.session.add(
            Asset(
                asset_code="ASSET-SUPPLIER-REFERENCE",
                asset_name="引用资产",
                status=AssetStatus.IDLE.value,
                organization_id=organization.id,
                category_id=category.id,
                unit_id=unit.id,
                supplier_id=supplier_id,
                original_amount=Decimal("1.00"),
                purchase_date=date(2026, 7, 23),
                service_life_months=36,
                expected_expiry_date=date(2029, 7, 23),
                manager_id=manager.id,
                source_id=source.id,
                location_id=location.id,
                custom_attributes={},
                data_completeness=AssetDataCompleteness.COMPLETE.value,
            )
        )
    else:
        operation = OperationRequest(
            request_no="STOCK-IN-SUPPLIER-REFERENCE",
            operation_type=OperationType.STOCK_IN.value,
            applicant_id=manager.id,
            approval_status=ApprovalStatus.PENDING.value,
            execution_status=ExecutionStatus.NOT_STARTED.value,
            flow_version=1,
        )
        db.session.add(operation)
        db.session.flush()
        request = StockInRequest(
            operation_request_id=operation.id, organization_id=organization.id
        )
        db.session.add(request)
        db.session.flush()
        db.session.add(
            StockInItem(
                stock_in_request_id=request.id,
                asset_code="STOCK-IN-SUPPLIER-REFERENCE",
                asset_name="引用入库项",
                category_id=category.id,
                unit_id=unit.id,
                supplier_id=supplier_id,
                original_amount=Decimal("1.00"),
                purchase_date=date(2026, 7, 23),
                service_life_months=36,
                expected_expiry_date=date(2029, 7, 23),
                manager_id=manager.id,
                source_id=source.id,
                location_id=location.id,
                custom_attributes={},
            )
        )
    db.session.commit()


@pytest.mark.parametrize("reference_type", ["asset", "stock_in"])
def test_asset_or_stock_in_reference_blocks_supplier_deletion(
    app, reference_type: str
) -> None:
    actor_id = _grant_actor()
    created = _create_supplier(actor_id)
    _add_supplier_reference(created["id"], reference_type)

    assert asset_repository.has_supplier_reference(created["id"]) is (
        reference_type == "asset"
    )
    assert stock_in_item_repository.has_supplier_reference(created["id"]) is (
        reference_type == "stock_in"
    )
    with pytest.raises(BusinessException, match="供应商已被使用，不能删除"):
        supplier_service.delete_supplier(
            created["id"], created["version"], actor_id, "不再合作"
        )
    assert db.session.get(Supplier, created["id"]) is not None


def test_unique_constraint_race_is_translated_without_sql_details(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()

    def collide(_supplier: Supplier) -> Supplier:
        raise IntegrityError(
            "INSERT INTO suppliers secret SQL",
            {},
            RuntimeError("UNIQUE constraint failed: suppliers.name"),
        )

    monkeypatch.setattr(supplier_repository, "add", collide)
    with pytest.raises(BusinessException) as caught:
        _create_supplier(actor_id)
    assert str(caught.value) == "供应商已存在"
    assert "INSERT" not in str(caught.value)
    assert db.session.query(SupplierCodeSequence).count() == 0


def test_unrecognized_create_integrity_error_is_a_safe_internal_failure(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()

    def collide(_supplier: Supplier) -> Supplier:
        raise IntegrityError(
            "INSERT INTO operation_logs secret SQL",
            {},
            RuntimeError("FOREIGN KEY constraint failed"),
        )

    monkeypatch.setattr(supplier_repository, "add", collide)
    with pytest.raises(BusinessException) as caught:
        _create_supplier(actor_id)
    assert caught.value.code == ResultCode.INTERNAL_ERROR.code
    assert "secret SQL" not in str(caught.value)
    assert db.session.query(SupplierCodeSequence).count() == 0


def test_sequence_allocation_integrity_error_rolls_back_and_is_safe(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()

    def collide() -> SupplierCodeSequence | None:
        raise IntegrityError(
            "INSERT INTO operation_logs secret SQL",
            {},
            RuntimeError("FOREIGN KEY constraint failed"),
        )

    monkeypatch.setattr(supplier_code_sequence_repository, "find_for_update", collide)
    with pytest.raises(BusinessException) as caught:
        _create_supplier(actor_id)
    assert caught.value.code == ResultCode.INTERNAL_ERROR.code
    assert "secret SQL" not in str(caught.value)
    assert db.session.query(SupplierCodeSequence).count() == 0
    assert db.session.query(Supplier).count() == 0


def test_enable_integrity_error_rolls_back_and_is_safe(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()
    created = _create_supplier(actor_id)

    def collide() -> None:
        raise IntegrityError(
            "INSERT INTO operation_logs secret SQL",
            {},
            RuntimeError("FOREIGN KEY constraint failed"),
        )

    monkeypatch.setattr(db.session, "commit", collide)
    with pytest.raises(BusinessException) as caught:
        supplier_service.set_supplier_enabled(
            created["id"], False, created["version"], actor_id
        )
    assert caught.value.code == ResultCode.INTERNAL_ERROR.code
    assert "secret SQL" not in str(caught.value)
    db.session.expire_all()
    persisted = db.session.get(Supplier, created["id"])
    assert persisted is not None
    assert persisted.status == RecordStatus.ENABLED.value
    assert persisted.version == created["version"]
    assert (
        db.session.query(OperationLog).filter_by(action="SUPPLIER_DISABLE").count() == 0
    )


def test_delete_fk_race_is_translated_and_rolled_back(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()
    created = _create_supplier(actor_id)

    def collide() -> None:
        raise IntegrityError(
            "DELETE FROM suppliers WHERE suppliers.id = ?",
            {},
            RuntimeError("FOREIGN KEY constraint failed"),
        )

    monkeypatch.setattr(db.session, "commit", collide)
    with pytest.raises(BusinessException) as caught:
        supplier_service.delete_supplier(
            created["id"], created["version"], actor_id, "合同终止"
        )
    assert str(caught.value) == "供应商已被使用，不能删除"
    assert "DELETE" not in str(caught.value)
    assert db.session.get(Supplier, created["id"]) is not None


def test_unrecognized_delete_integrity_error_is_a_safe_internal_failure(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id = _grant_actor()
    created = _create_supplier(actor_id)

    def collide() -> None:
        raise IntegrityError(
            "INSERT INTO operation_logs secret SQL",
            {},
            RuntimeError("FOREIGN KEY constraint failed"),
        )

    monkeypatch.setattr(db.session, "commit", collide)
    with pytest.raises(BusinessException) as caught:
        supplier_service.delete_supplier(
            created["id"], created["version"], actor_id, "合同终止"
        )
    assert caught.value.code == ResultCode.INTERNAL_ERROR.code
    assert "secret SQL" not in str(caught.value)
    assert db.session.get(Supplier, created["id"]) is not None


def test_delete_fk_constraint_closes_stale_reference_check_across_transactions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "supplier-delete-fk-race.db")
    with concurrent_app.app_context():
        db.create_all()
        actor_id = _grant_actor("delete-race-actor")
        created = _create_supplier(actor_id)
        assert asset_repository.has_supplier_reference(created["id"]) is False

    with concurrent_app.app_context():
        _add_supplier_reference(created["id"], "asset")

    monkeypatch.setattr(
        asset_repository, "has_supplier_reference", lambda _supplier_id: False
    )
    monkeypatch.setattr(
        stock_in_item_repository,
        "has_supplier_reference",
        lambda _supplier_id: False,
    )
    with concurrent_app.app_context():
        with pytest.raises(BusinessException, match="供应商已被使用，不能删除"):
            supplier_service.delete_supplier(
                created["id"], created["version"], actor_id, "并发引用"
            )
        assert db.session.get(Supplier, created["id"]) is not None
        assert db.session.query(Asset).filter_by(supplier_id=created["id"]).count() == 1
        db.drop_all()


def test_first_supplier_codes_are_safe_across_independent_transactions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "supplier-code-concurrency.db")
    with concurrent_app.app_context():
        db.create_all()
        actor_id = _grant_actor("concurrent-code-actor")

    allocation_barrier = Barrier(2, timeout=10)
    original_ensure_exists = supplier_code_sequence_repository.ensure_exists

    def synchronized_ensure_exists() -> None:
        allocation_barrier.wait()
        original_ensure_exists()

    monkeypatch.setattr(
        supplier_code_sequence_repository,
        "ensure_exists",
        synchronized_ensure_exists,
    )

    def create_once(index: int) -> str:
        with concurrent_app.app_context():
            return supplier_service.create_supplier(
                _payload(f"并发供应商-{index}", f"credit-{index}"), actor_id
            )["code"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        codes = list(executor.map(create_once, range(2)))

    assert sorted(codes) == ["SUP000001", "SUP000002"]
    with concurrent_app.app_context():
        sequence = db.session.get(SupplierCodeSequence, "SUP")
        assert sequence is not None
        assert sequence.current_value == 2
        assert db.session.query(Supplier).count() == 2
        db.drop_all()


def test_same_version_concurrent_cas_has_one_winner_and_one_stale_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "supplier-cas-concurrency.db")
    with concurrent_app.app_context():
        db.create_all()
        actor_id = _grant_actor("concurrent-cas-actor")
        created = _create_supplier(actor_id)
        supplier_id = created["id"]
        expected_version = created["version"]

    barrier = Barrier(2, timeout=10)
    original_cas_update = supplier_repository.cas_update

    def synchronized_cas_update(
        target_supplier_id: int,
        target_version: int,
        changes: dict[str, object],
    ) -> bool:
        barrier.wait()
        return original_cas_update(target_supplier_id, target_version, changes)

    monkeypatch.setattr(supplier_repository, "cas_update", synchronized_cas_update)

    def update_once(index: int) -> tuple[str, str]:
        with concurrent_app.app_context():
            try:
                result = supplier_service.update_supplier(
                    supplier_id,
                    {"name": f"并发更新-{index}", "version": expected_version},
                    actor_id,
                )
                return "success", result["name"]
            except BusinessException as error:
                return "stale", str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(update_once, range(2)))

    assert sorted(outcome[0] for outcome in outcomes) == ["stale", "success"]
    with concurrent_app.app_context():
        persisted = db.session.get(Supplier, supplier_id)
        assert persisted is not None
        assert persisted.version == expected_version + 1
        assert persisted.name in {"并发更新-0", "并发更新-1"}
        assert (
            db.session.query(OperationLog).filter_by(action="SUPPLIER_UPDATE").count()
            == 1
        )
        db.drop_all()


def test_http_supplier_lifecycle_closes_status_and_version_loop(client) -> None:
    headers = _supplier_http_headers(client)

    created_response = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={"name": "接口供应商"},
    )
    assert created_response.status_code == 200
    created = created_response.get_json()["data"]
    assert created["code"] == "SUP000001"
    assert created["name"] == "接口供应商"
    assert created["status"] == RecordStatus.ENABLED.value
    assert created["version"] == 1

    updated_response = client.post(
        f"/api/v1/suppliers/{created['id']}/update",
        headers=headers,
        json={"name": "接口供应商有限公司", "version": 1},
    )
    assert updated_response.status_code == 200
    updated = updated_response.get_json()["data"]
    assert updated["name"] == "接口供应商有限公司"
    assert updated["status"] == RecordStatus.ENABLED.value
    assert updated["version"] == 2

    listed_response = client.get("/api/v1/suppliers", headers=headers)
    assert listed_response.status_code == 200
    assert listed_response.get_json()["data"] == [updated]

    disabled_response = client.post(
        f"/api/v1/suppliers/{created['id']}/disable",
        headers=headers,
        json={"version": updated["version"]},
    )
    assert disabled_response.status_code == 200
    disabled = disabled_response.get_json()["data"]
    assert disabled["status"] == RecordStatus.DISABLED.value
    assert disabled["version"] == 3

    enabled_response = client.post(
        f"/api/v1/suppliers/{created['id']}/enable",
        headers=headers,
        json={"version": disabled["version"]},
    )
    assert enabled_response.status_code == 200
    enabled = enabled_response.get_json()["data"]
    assert enabled["status"] == RecordStatus.ENABLED.value
    assert enabled["version"] == 4

    deleted_response = client.post(
        f"/api/v1/suppliers/{created['id']}/delete",
        headers=headers,
        json={"version": enabled["version"], "reason": "测试删除"},
    )
    assert deleted_response.status_code == 200
    deleted_body = deleted_response.get_json()
    assert deleted_body["code"] == 200
    assert deleted_body["message"] == "OK"
    assert deleted_body["request_id"]
    assert client.get("/api/v1/suppliers", headers=headers).get_json()["data"] == []


def test_http_supplier_routes_require_jwt_and_exact_permission(client) -> None:
    unauthorized = client.get("/api/v1/suppliers")
    assert unauthorized.status_code == 401
    assert unauthorized.get_json()["code"] == ResultCode.UNAUTHORIZED.code

    view_only_headers = _supplier_http_headers(
        client,
        username="supplier-http-viewer",
        permission_codes=("supplier:view",),
    )
    forbidden = client.post(
        "/api/v1/suppliers",
        headers=view_only_headers,
        json={"name": "无创建权限供应商"},
    )
    assert forbidden.status_code == 200
    assert forbidden.get_json()["code"] == ResultCode.FORBIDDEN.code


def test_http_supplier_payload_validation_rejects_malformed_and_blank_text(
    client,
) -> None:
    headers = _supplier_http_headers(client)

    malformed = client.post(
        "/api/v1/suppliers",
        headers=headers,
        data="{",
        content_type="application/json",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["code"] == ResultCode.BAD_REQUEST.code

    blank_create = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={"name": "   "},
    )
    assert blank_create.status_code == 400
    assert "供应商名称不能为空" in blank_create.get_json()["message"]

    created = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={"name": "待校验供应商"},
    ).get_json()["data"]
    blank_update = client.post(
        f"/api/v1/suppliers/{created['id']}/update",
        headers=headers,
        json={"name": "   ", "version": created["version"]},
    )
    assert blank_update.status_code == 400
    assert "供应商名称不能为空" in blank_update.get_json()["message"]

    blank_delete = client.post(
        f"/api/v1/suppliers/{created['id']}/delete",
        headers=headers,
        json={"version": created["version"], "reason": "   "},
    )
    assert blank_delete.status_code == 400
    assert "删除原因不能为空" in blank_delete.get_json()["message"]


def test_http_supplier_blueprint_keeps_boundary_and_get_post_only(app) -> None:
    routes = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/v1/suppliers")
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }
    assert routes == {
        ("/api/v1/suppliers", "GET"),
        ("/api/v1/suppliers", "POST"),
        ("/api/v1/suppliers/<int:supplier_id>/update", "POST"),
        ("/api/v1/suppliers/<int:supplier_id>/disable", "POST"),
        ("/api/v1/suppliers/<int:supplier_id>/enable", "POST"),
        ("/api/v1/suppliers/<int:supplier_id>/delete", "POST"),
    }

    source_path = Path(__file__).parents[1] / "app" / "api" / "suppliers.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    import_targets = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    from_imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert all(node.level == 0 and node.module is not None for node in from_imports)
    import_targets.update(
        f"{node.module}.{alias.name}" for node in from_imports for alias in node.names
    )
    assert not any(
        target == "app.models" or target.startswith("app.models.")
        for target in import_targets
    )
    assert not any(
        target == "app.extensions" or target.startswith("app.extensions.")
        for target in import_targets
    )

    service_imports = {
        target
        for target in import_targets
        if target == "app.services" or target.startswith("app.services.")
    }
    assert service_imports == {"app.services.supplier_service"}

    blueprint_decorators = {
        decorator.func.attr
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "bp"
    }
    assert blueprint_decorators == {"get", "post"}

    supplier_service_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "supplier_service"
    }
    assert supplier_service_calls == {
        "create_supplier",
        "delete_supplier",
        "list_suppliers",
        "set_supplier_enabled",
        "update_supplier",
    }
