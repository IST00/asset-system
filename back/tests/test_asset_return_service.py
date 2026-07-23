"""Personal and public asset-return service and handler contracts."""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from app import create_app
from app.common import BusinessException
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetStatus,
    DataScope,
    ExecutionStatus,
    OperationType,
    RecordStatus,
    UsageType,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetLifecycleRecord,
    OperationActionIdempotency,
    OperationExecutionAttempt,
    OperationLog,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    PublicUsageObject,
    User,
)
from app.models.asset_usage_return import AssetReturnItem, AssetReturnRequest
from app.operations.registry import operation_handler_registry
from app.services import approval_provider_service, operation_service
from asset_usage_return_fixtures import (
    UsageReturnContext,
    grant_permissions,
    grant_scoped_manager_permission,
    register_usage_return_handlers,
    seed_usage_return_context,
)
from config import TestConfig


def _return_service() -> ModuleType:
    try:
        return importlib.import_module("app.services.asset_return_service")
    except ModuleNotFoundError as error:
        raise AssertionError("missing asset_return_service") from error


def _handler_module() -> ModuleType:
    return importlib.import_module("app.operations.asset_usage_return_handlers")


def _set_personal_in_use(
    context: UsageReturnContext,
    *,
    holder_id: int | None = None,
) -> None:
    holder = holder_id if holder_id is not None else context.employee.id
    for asset in (context.main_asset, context.child_asset):
        asset.status = AssetStatus.IN_USE.value
        asset.usage_type = UsageType.PERSONAL.value
        asset.holder_user_id = holder
        asset.public_object_id = None
        asset.usage_department_id = context.organization.id
    db.session.flush()


def _set_public_in_use(context: UsageReturnContext) -> None:
    for asset in (context.main_asset, context.child_asset):
        asset.status = AssetStatus.IN_USE.value
        asset.usage_type = UsageType.PUBLIC.value
        asset.holder_user_id = None
        asset.public_object_id = context.public_object.id
        asset.usage_department_id = None
    db.session.flush()


def _grant_self_return(context: UsageReturnContext) -> None:
    role = grant_permissions(context.employee, "asset:return:self")
    role.data_scope = DataScope.SELF.value
    db.session.flush()


def _grant_return_manage(context: UsageReturnContext) -> None:
    grant_permissions(context.manager, "asset:usage:manage")


def _personal_payload(
    context: UsageReturnContext,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"asset_ids": [context.main_asset.id]}
    if key is not None:
        payload["idempotency_key"] = key
    return payload


def _inspection_payload(
    context: UsageReturnContext,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "return_location_id": context.return_location.id,
        "items": [
            {"asset_id": context.main_asset.id, "condition": "NORMAL"},
            {
                "asset_id": context.child_asset.id,
                "condition": "DAMAGED",
                "condition_description": "  外壳划痕  ",
            },
        ],
    }
    if key is not None:
        payload["idempotency_key"] = key
    return payload


def _assets(context: UsageReturnContext) -> list[Asset]:
    db.session.expire_all()
    rows = [
        db.session.get(Asset, context.main_asset.id),
        db.session.get(Asset, context.child_asset.id),
    ]
    assert all(row is not None for row in rows)
    return [row for row in rows if row is not None]


def _approve_personal(result: dict[str, Any], actor_id: int) -> OperationRequest:
    return approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id=f"return-approved-{result['id']}",
        external_instance_id=result["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=actor_id,
    )


def _assert_no_return_aggregate() -> None:
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(OperationRequestAsset).count() == 0
    assert db.session.query(AssetReturnRequest).count() == 0
    assert db.session.query(AssetReturnItem).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 0


def _stage_pending_organization(
    pending_kind: str,
    sentinel: Organization,
    suffix: str,
) -> Organization:
    if pending_kind == "new":
        pending = Organization(
            code=f"UR-PENDING-{suffix}",
            name=f"UR Pending {suffix}",
            status=RecordStatus.ENABLED.value,
        )
        db.session.add(pending)
        return pending
    if pending_kind == "dirty":
        sentinel.name = f"UR Dirty {suffix}"
        return sentinel
    db.session.delete(sentinel)
    return sentinel


def _assert_pending_organization_survives(
    pending_kind: str,
    pending: Organization,
) -> None:
    session = db.session()
    if pending_kind == "new":
        assert pending in session.new
        db.session.commit()
        assert pending.id is not None
        return
    if pending_kind == "dirty":
        assert pending in session.dirty
        expected_name = pending.name
        pending_id = pending.id
        db.session.commit()
        persisted = db.session.get(Organization, pending_id)
        assert persisted is not None
        assert persisted.name == expected_name
        return
    assert pending in session.deleted
    db.session.rollback()
    pending_id = pending.id
    assert db.session.get(Organization, pending_id) is not None


def test_return_applicant_can_view_own_detail_and_page(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )

    detail = service.get(submitted["id"], context.employee.id)
    result = service.page(
        actor_id=context.employee.id,
        page_index=0,
        size=10,
    )

    assert detail["id"] == submitted["id"]
    assert detail["feature"]["items"] == submitted["feature"]["items"]
    assert detail["allowed_actions"] == []
    assert result.total == 1
    assert result.items == [detail]


def test_return_manager_visibility_requires_scope_over_every_snapshot(app) -> None:
    context = seed_usage_return_context()
    other_organization = Organization(
        code="UR-RETURN-QUERY-OTHER",
        name="UR Return Query Other",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(other_organization)
    db.session.flush()
    context.child_asset.organization_id = other_organization.id
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    grant_scoped_manager_permission(context.manager, context.organization.id)
    db.session.commit()

    with pytest.raises(BusinessException, match="无权查看"):
        service.get(submitted["id"], context.manager.id)
    partial_page = service.page(
        actor_id=context.manager.id,
        page_index=0,
        size=10,
    )

    assert partial_page.total == 0

    grant_scoped_manager_permission(context.manager, other_organization.id)
    db.session.commit()

    detail = service.get(submitted["id"], context.manager.id)
    full_page = service.page(
        actor_id=context.manager.id,
        page_index=0,
        size=10,
    )

    assert detail["id"] == submitted["id"]
    assert len(detail["assets"]) == 2
    assert full_page.total == 1
    assert [item["id"] for item in full_page.items] == [submitted["id"]]


def test_return_limited_scope_manager_cannot_view_request_without_snapshots(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    grant_scoped_manager_permission(context.manager, context.organization.id)
    db.session.query(OperationRequestAsset).filter(
        OperationRequestAsset.operation_request_id == submitted["id"]
    ).delete(synchronize_session=False)
    db.session.commit()

    with pytest.raises(BusinessException, match="无权查看"):
        service.get(submitted["id"], context.manager.id)

    result = service.page(
        actor_id=context.manager.id,
        page_index=0,
        size=10,
    )

    assert result.total == 0
    assert result.items == []


def test_return_pages_isolate_applicants_and_use_stable_newest_first_order(
    app,
) -> None:
    context = seed_usage_return_context()
    context.child_asset.parent_asset_id = None
    _set_personal_in_use(context)
    context.child_asset.holder_user_id = context.manager.id
    _grant_self_return(context)
    manager_role = grant_permissions(context.manager, "asset:return:self")
    manager_role.data_scope = DataScope.SELF.value
    db.session.flush()
    service = _return_service()
    first = service.submit_personal(
        {"asset_ids": [context.main_asset.id]},
        context.employee.id,
    )
    second = service.submit_personal(
        {"asset_ids": [context.child_asset.id]},
        context.manager.id,
    )
    operation_service.release_locks(first["id"])
    db.session.commit()
    third = service.submit_personal(
        {"asset_ids": [context.main_asset.id]},
        context.employee.id,
    )
    same_created_at = datetime(2026, 7, 22, 1, 2, 3, tzinfo=timezone.utc)
    first_operation = db.session.get(OperationRequest, first["id"])
    second_operation = db.session.get(OperationRequest, second["id"])
    third_operation = db.session.get(OperationRequest, third["id"])
    assert first_operation is not None
    assert second_operation is not None
    assert third_operation is not None
    first_operation.created_at = same_created_at
    second_operation.created_at = same_created_at
    third_operation.created_at = datetime(
        2026,
        7,
        21,
        1,
        2,
        3,
        tzinfo=timezone.utc,
    )
    db.session.commit()

    employee_page = service.page(
        actor_id=context.employee.id,
        page_index=0,
        size=10,
    )
    manager_own_page = service.page(
        actor_id=context.manager.id,
        page_index=0,
        size=10,
    )

    assert employee_page.total == 2
    assert [item["id"] for item in employee_page.items] == [
        first["id"],
        third["id"],
    ]
    assert manager_own_page.total == 1
    assert [item["id"] for item in manager_own_page.items] == [second["id"]]

    grant_permissions(context.manager, "asset:usage:manage")
    db.session.commit()

    newest_page = service.page(
        actor_id=context.manager.id,
        page_index=0,
        size=1,
    )
    older_page = service.page(
        actor_id=context.manager.id,
        page_index=1,
        size=1,
    )
    oldest_page = service.page(
        actor_id=context.manager.id,
        page_index=2,
        size=1,
    )

    assert newest_page.total == 3
    assert [item["id"] for item in newest_page.items] == [second["id"]]
    assert older_page.total == 3
    assert [item["id"] for item in older_page.items] == [first["id"]]
    assert oldest_page.total == 3
    assert [item["id"] for item in oldest_page.items] == [third["id"]]


def test_return_page_query_count_is_constant_when_page_size_grows(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()
    for _index in range(5):
        submitted = service.submit_personal(
            _personal_payload(context),
            context.employee.id,
        )
        operation_service.release_locks(submitted["id"])
        db.session.commit()
    actor_id = context.employee.id
    engine = db.engine

    def count_page(size: int) -> tuple[Any, int]:
        db.session.remove()
        select_count = 0

        def record_statement(*args: object) -> None:
            nonlocal select_count
            if str(args[2]).lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            result = service.page(actor_id=actor_id, page_index=0, size=size)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)
        return result, select_count

    size_one, size_one_selects = count_page(1)
    size_five, size_five_selects = count_page(5)

    assert size_one.total == 5
    assert size_five.total == 5
    assert size_one.items == size_five.items[:1]
    assert size_five_selects <= size_one_selects + 1, (
        size_one_selects,
        size_five_selects,
    )


def test_return_page_preloaded_rows_still_require_complete_inspection_items(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()
    service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    db.session.delete(db.session.query(AssetReturnItem).first())
    db.session.commit()

    with pytest.raises(BusinessException, match="明细不完整"):
        service.page(
            actor_id=context.employee.id,
            page_index=0,
            size=10,
        )


def test_confirm_return_action_requires_approved_personal_request_and_full_scope(
    app,
) -> None:
    context = seed_usage_return_context()
    other_organization = Organization(
        code="UR-ACTION-OTHER",
        name="UR Action Other",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(other_organization)
    db.session.flush()
    context.child_asset.organization_id = other_organization.id
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    grant_scoped_manager_permission(context.manager, context.organization.id)
    grant_scoped_manager_permission(context.manager, other_organization.id)
    db.session.commit()

    pending_detail = service.get(submitted["id"], context.manager.id)

    assert pending_detail["allowed_actions"] == []

    _approve_personal(submitted, context.manager.id)

    manager_detail = service.get(submitted["id"], context.manager.id)
    manager_page = service.page(
        actor_id=context.manager.id,
        page_index=0,
        size=10,
    )
    applicant_detail = service.get(submitted["id"], context.employee.id)
    applicant_page = service.page(
        actor_id=context.employee.id,
        page_index=0,
        size=10,
    )

    assert manager_detail["allowed_actions"] == ["CONFIRM_RETURN"]
    assert manager_page.items[0]["allowed_actions"] == ["CONFIRM_RETURN"]
    assert applicant_detail["allowed_actions"] == []
    assert applicant_page.items[0]["allowed_actions"] == []


def test_personal_return_applicant_cannot_receive_confirm_action_with_manage_scope(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    grant_permissions(
        context.employee,
        "asset:return:self",
        "asset:usage:manage",
    )
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)

    detail = service.get(submitted["id"], context.employee.id)
    result = service.page(
        actor_id=context.employee.id,
        page_index=0,
        size=10,
    )

    assert detail["approval_status"] == ApprovalStatus.APPROVED.value
    assert detail["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert detail["approval_execution_mode"] == (
        ApprovalExecutionMode.MANUAL_CONFIRM.value
    )
    assert detail["allowed_actions"] == []
    assert result.items[0]["allowed_actions"] == []


def test_personal_return_applicant_cannot_confirm_own_request_with_manage_scope(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    grant_permissions(
        context.employee,
        "asset:return:self",
        "asset:usage:manage",
    )
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)

    with pytest.raises(BusinessException, match="申请人不能验收"):
        service.confirm(
            submitted["id"],
            _inspection_payload(context),
            context.employee.id,
        )

    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    assert operation.approval_status == ApprovalStatus.APPROVED.value
    assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
    detail = db.session.query(AssetReturnRequest).one()
    assert detail.return_location_id is None
    assert detail.confirmed_by is None
    assert detail.confirmed_at is None
    assert all(item.condition is None for item in db.session.query(AssetReturnItem))
    assert db.session.query(OperationActionIdempotency).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2


def test_public_return_never_offers_manual_confirm_action(app) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    payload = _inspection_payload(context)
    payload["asset_ids"] = [context.main_asset.id]
    submitted = service.submit_public(
        payload,
        context.manager.id,
    )
    snapshot = (
        db.session.query(OperationRequestAsset)
        .filter(OperationRequestAsset.asset_id == context.main_asset.id)
        .one()
    )
    original_asset_name = snapshot.asset_name_snapshot
    original_public_object_name = snapshot.before_data["public_object_name"]
    original_location_name = snapshot.location_snapshot["name"]
    context.main_asset.asset_name = "UR Current Renamed Return Asset"
    context.public_object.name = "UR Current Renamed Public Object"
    context.public_object.status = RecordStatus.DISABLED.value
    context.location.name = "UR Current Renamed Return Origin"
    context.location.status = RecordStatus.DISABLED.value
    context.return_location.name = "UR Current Renamed Return Destination"
    context.return_location.status = RecordStatus.DISABLED.value
    db.session.commit()

    detail = service.get(submitted["id"], context.manager.id)

    assert detail["operation_type"] == OperationType.PUBLIC_RETURN.value
    assert detail["approval_status"] == ApprovalStatus.APPROVED.value
    assert detail["allowed_actions"] == []
    asset_detail = next(
        item for item in detail["assets"] if item["asset_id"] == context.main_asset.id
    )
    assert asset_detail["asset_name"] == original_asset_name
    assert asset_detail["before_data"]["public_object_name"] == (
        original_public_object_name
    )
    assert asset_detail["location_snapshot"]["name"] == original_location_name
    assert detail["feature"]["return_location_id"] == context.return_location.id
    assert detail["feature"]["items"] == submitted["feature"]["items"]


def test_return_handlers_expose_exact_types_and_safe_messages() -> None:
    module = _handler_module()

    assert module.PersonalReturnHandler.operation_type == (
        OperationType.PERSONAL_RETURN.value
    )
    assert (
        module.PersonalReturnHandler.safe_error_message
        == "个人退库执行失败，请联系管理员或稍后重试"
    )
    assert (
        module.PublicReturnHandler.operation_type == OperationType.PUBLIC_RETURN.value
    )
    assert (
        module.PublicReturnHandler.safe_error_message
        == "公共资产退回执行失败，请联系管理员或稍后重试"
    )


def test_personal_submission_expands_child_without_organization_scope(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)

    result = _return_service().submit_personal(
        _personal_payload(context),
        context.employee.id,
    )

    assert result["operation_type"] == OperationType.PERSONAL_RETURN.value
    assert result["approval_channel"] == ApprovalChannel.FEISHU.value
    assert (
        result["approval_execution_mode"] == ApprovalExecutionMode.MANUAL_CONFIRM.value
    )
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    assert result["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert result["external_instance_id"] == f"LOCAL-FEISHU-{result['id']}"
    assert [item["asset_id"] for item in result["assets"]] == [
        context.main_asset.id,
        context.child_asset.id,
    ]
    for item in result["assets"]:
        assert item["target_data"] == {
            "status": AssetStatus.IDLE.value,
            "usage_type": None,
            "holder_user_id": None,
            "public_object_id": None,
            "usage_department_id": None,
        }
    assert result["feature"] == {
        "return_location_id": None,
        "return_location_snapshot": None,
        "confirmed_by": None,
        "confirmed_by_snapshot": None,
        "confirmed_at": None,
        "items": [
            {
                "asset_id": context.main_asset.id,
                "condition": None,
                "condition_description": None,
            },
            {
                "asset_id": context.child_asset.id,
                "condition": None,
                "condition_description": None,
            },
        ],
    }
    detail = db.session.query(AssetReturnRequest).one()
    assert detail.return_location_id is None
    assert detail.return_location_snapshot is None
    assert detail.confirmed_by is None
    assert detail.confirmed_by_snapshot is None
    assert detail.confirmed_at is None
    assert db.session.query(AssetReturnItem).count() == 2
    assert all(
        item.condition is None and item.condition_description is None
        for item in db.session.query(AssetReturnItem).all()
    )
    assert db.session.query(AssetBusinessLock).count() == 2
    assert db.session.query(OperationExecutionAttempt).count() == 0


@pytest.mark.parametrize("invalid", ["other-holder", "idle", "public", "child"])
def test_personal_submission_rejects_invalid_expanded_assets_without_writes(
    app,
    invalid: str,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    if invalid == "other-holder":
        context.main_asset.holder_user_id = context.manager.id
    elif invalid == "idle":
        context.main_asset.status = AssetStatus.IDLE.value
    elif invalid == "public":
        context.main_asset.usage_type = UsageType.PUBLIC.value
        context.main_asset.holder_user_id = None
        context.main_asset.public_object_id = context.public_object.id
    else:
        context.child_asset.holder_user_id = context.manager.id

    with pytest.raises(BusinessException):
        _return_service().submit_personal(
            _personal_payload(context),
            context.employee.id,
        )

    _assert_no_return_aggregate()


def test_personal_submission_replays_one_intact_aggregate_before_mutable_checks(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()

    created = service.submit_personal(
        _personal_payload(context, key="  personal-return-once  "),
        context.employee.id,
    )
    context.main_asset.status = AssetStatus.IDLE.value
    replayed = service.submit_personal(
        {"asset_ids": [999_999], "idempotency_key": "personal-return-once"},
        context.employee.id,
    )

    assert replayed == created
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(AssetReturnRequest).count() == 1
    assert db.session.query(AssetReturnItem).count() == 2
    assert db.session.query(AssetBusinessLock).count() == 2
    assert db.session.query(OperationExecutionAttempt).count() == 0


@pytest.mark.parametrize(
    "corruption",
    ["missing-detail", "missing-item", "filled-item", "target"],
)
def test_personal_submission_replay_validates_return_aggregate_integrity(
    app,
    corruption: str,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    service = _return_service()
    service.submit_personal(
        _personal_payload(context, key=f"personal-corrupt-{corruption}"),
        context.employee.id,
    )
    if corruption == "missing-detail":
        db.session.delete(db.session.query(AssetReturnRequest).one())
    elif corruption == "missing-item":
        db.session.delete(db.session.query(AssetReturnItem).first())
    elif corruption == "filled-item":
        db.session.query(AssetReturnItem).first().condition = "NORMAL"
    else:
        snapshot = db.session.query(OperationRequestAsset).first()
        snapshot.target_data = {
            **snapshot.target_data,
            "location_id": context.location.id,
        }
        flag_modified(snapshot, "target_data")
    db.session.commit()

    with pytest.raises(BusinessException):
        service.submit_personal(
            {
                "asset_ids": [999_999],
                "idempotency_key": f"personal-corrupt-{corruption}",
            },
            context.employee.id,
        )

    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 0


def test_personal_confirm_rejects_forged_before_snapshot(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    snapshot = db.session.query(OperationRequestAsset).first()
    snapshot.before_data = {
        **snapshot.before_data,
        "public_object_name": "FORGED",
        "unexpected": True,
    }
    flag_modified(snapshot, "before_data")
    db.session.commit()

    with pytest.raises(BusinessException):
        service.confirm(
            submitted["id"],
            _inspection_payload(context),
            context.manager.id,
        )

    detail = db.session.query(AssetReturnRequest).one()
    assert detail.confirmed_by is None
    assert all(item.condition is None for item in db.session.query(AssetReturnItem))
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2


def test_personal_approval_waits_for_inspection_and_retains_locks(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    submitted = _return_service().submit_personal(
        _personal_payload(context),
        context.employee.id,
    )

    approved = _approve_personal(submitted, context.manager.id)

    assert approved.approval_status == ApprovalStatus.APPROVED.value
    assert approved.execution_status == ExecutionStatus.NOT_STARTED.value
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2
    assert [asset.status for asset in _assets(context)] == [
        AssetStatus.IN_USE.value,
        AssetStatus.IN_USE.value,
    ]


def test_personal_rejection_leaves_assets_unchanged_and_releases_locks(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    rejected_submission = _return_service().submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    rejected = approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id="personal-return-rejected",
        external_instance_id=rejected_submission["external_instance_id"],
        status=ApprovalStatus.REJECTED.value,
        actor_id=context.manager.id,
    )
    assert rejected.approval_status == ApprovalStatus.REJECTED.value
    assert rejected.execution_status == ExecutionStatus.NOT_STARTED.value
    assert [asset.status for asset in _assets(context)] == [
        AssetStatus.IN_USE.value,
        AssetStatus.IN_USE.value,
    ]
    assert db.session.query(AssetBusinessLock).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 0


def test_personal_withdrawal_leaves_assets_unchanged_and_releases_locks(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    submitted = _return_service().submit_personal(
        _personal_payload(context),
        context.employee.id,
    )

    withdrawn = approval_provider_service.withdraw(
        submitted["id"],
        context.employee.id,
    )

    assert withdrawn.approval_status == ApprovalStatus.WITHDRAWN.value
    assert withdrawn.execution_status == ExecutionStatus.NOT_STARTED.value
    assert [asset.status for asset in _assets(context)] == [
        AssetStatus.IN_USE.value,
        AssetStatus.IN_USE.value,
    ]
    assert db.session.query(AssetBusinessLock).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 0


def test_personal_confirmation_returns_normal_and_damaged_assets_atomically(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)

    result = service.confirm(
        submitted["id"],
        _inspection_payload(context, key="confirm-once"),
        context.manager.id,
    )

    assert result["approval_status"] == ApprovalStatus.APPROVED.value
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert result["feature"]["return_location_id"] == context.return_location.id
    assert result["feature"]["confirmed_by"] == context.manager.id
    assert result["feature"]["confirmed_at"] is not None
    assert result["feature"]["items"] == [
        {
            "asset_id": context.main_asset.id,
            "condition": "NORMAL",
            "condition_description": None,
        },
        {
            "asset_id": context.child_asset.id,
            "condition": "DAMAGED",
            "condition_description": "外壳划痕",
        },
    ]
    for asset in _assets(context):
        assert asset.status == AssetStatus.IDLE.value
        assert asset.usage_type is None
        assert asset.holder_user_id is None
        assert asset.public_object_id is None
        assert asset.usage_department_id is None
        assert asset.location_id == context.return_location.id
        assert asset.version == 2
    lifecycle = (
        db.session.query(AssetLifecycleRecord)
        .order_by(AssetLifecycleRecord.asset_id.asc())
        .all()
    )
    assert len(lifecycle) == 2
    assert lifecycle[0].after_data is not None
    assert lifecycle[0].after_data["return_condition"] == "NORMAL"
    assert lifecycle[0].after_data["condition_description"] is None
    assert lifecycle[1].after_data is not None
    assert lifecycle[1].after_data["return_condition"] == "DAMAGED"
    assert lifecycle[1].after_data["condition_description"] == "外壳划痕"
    log = db.session.query(OperationLog).one()
    assert log.before_data == {
        "asset_ids": [context.main_asset.id, context.child_asset.id],
        "asset_count": 2,
        "damaged_count": 1,
    }
    assert log.after_data == {"result": "SUCCESS"}
    assert db.session.query(OperationExecutionAttempt).one().status == "SUCCESS"
    assert db.session.query(AssetBusinessLock).count() == 0
    assert db.session.query(OperationActionIdempotency).one().status == "COMPLETED"


def test_personal_return_confirmation_snapshots_survive_master_data_changes(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    employee_id = context.employee.id
    manager_id = context.manager.id
    submitted = service.submit_personal(
        _personal_payload(context),
        employee_id,
    )
    _approve_personal(submitted, manager_id)
    payload = _inspection_payload(context, key="historical-confirmation")
    expected_location = {
        "id": context.return_location.id,
        "code": context.return_location.code,
        "name": context.return_location.name,
    }
    expected_confirmer = {
        "id": context.manager.id,
        "username": context.manager.username,
        "name": context.manager.nickname,
    }
    first = service.confirm(submitted["id"], payload, manager_id)
    context.return_location.name = "UR Return Location Renamed"
    context.return_location.status = RecordStatus.DISABLED.value
    context.manager.username = "UR-manager-renamed"
    context.manager.nickname = "UR Manager Renamed"
    db.session.commit()

    replayed = service.confirm(submitted["id"], payload, manager_id)
    manager = db.session.get(User, manager_id)
    assert manager is not None
    manager.enabled = False
    db.session.commit()
    detail = service.get(submitted["id"], employee_id)
    page_item = service.page(
        actor_id=employee_id,
        page_index=0,
        size=10,
    ).items[0]

    for item in (first, replayed, detail, page_item):
        feature = item["feature"]
        assert feature.get("return_location_snapshot") == expected_location
        assert feature.get("confirmed_by_snapshot") == expected_confirmer


def test_return_query_rejects_malformed_confirmation_snapshot(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    service.confirm(
        submitted["id"],
        _inspection_payload(context),
        context.manager.id,
    )
    detail = db.session.query(AssetReturnRequest).one()
    detail.confirmed_by_snapshot = {
        "id": context.manager.id,
        "username": context.manager.username,
    }
    db.session.commit()

    with pytest.raises(BusinessException, match="快照"):
        service.get(submitted["id"], context.manager.id)


def test_confirmation_same_key_and_no_key_replays_execute_once(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    payload = _inspection_payload(context, key="same-confirm")
    no_key_payload = _inspection_payload(context)
    actor_id = context.manager.id

    first = service.confirm(submitted["id"], payload, actor_id)
    keyed_replay = service.confirm(submitted["id"], payload, actor_id)
    no_key_replay = service.confirm(
        submitted["id"],
        no_key_payload,
        actor_id,
    )

    assert keyed_replay == first
    assert no_key_replay == first
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(OperationActionIdempotency).count() == 1


@pytest.mark.parametrize("difference", ["location", "items"])
def test_confirmation_same_key_rejects_different_payload(
    app,
    difference: str,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    payload = _inspection_payload(context, key="strict-confirm-replay")
    first = service.confirm(submitted["id"], payload, context.manager.id)
    conflicting_payload = _inspection_payload(context, key="strict-confirm-replay")
    if difference == "location":
        conflicting_payload["return_location_id"] = context.location.id
    else:
        conflicting_payload["items"] = [
            {
                "asset_id": context.main_asset.id,
                "condition": "DAMAGED",
                "condition_description": "新的验收结果",
            },
            {"asset_id": context.child_asset.id, "condition": "NORMAL"},
        ]

    with pytest.raises(BusinessException, match="其他验收请求"):
        service.confirm(
            submitted["id"],
            conflicting_payload,
            context.manager.id,
        )

    assert first["execution_status"] == ExecutionStatus.SUCCESS.value
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(OperationActionIdempotency).count() == 1


def test_completed_confirmation_rejects_new_key_with_same_payload(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    first = service.confirm(
        submitted["id"],
        _inspection_payload(context, key="completed-confirm-original"),
        context.manager.id,
    )

    with pytest.raises(BusinessException, match="其他验收请求"):
        service.confirm(
            submitted["id"],
            _inspection_payload(context, key="completed-confirm-new"),
            context.manager.id,
        )

    assert first["execution_status"] == ExecutionStatus.SUCCESS.value
    assert db.session.query(OperationExecutionAttempt).count() == 1
    claim = db.session.query(OperationActionIdempotency).one()
    assert claim.idempotency_key == "completed-confirm-original"


def test_successful_confirmation_replay_rejects_corrupt_target_snapshot(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    completed = service.confirm(
        submitted["id"],
        _inspection_payload(context),
        context.manager.id,
    )
    assert completed["execution_status"] == ExecutionStatus.SUCCESS.value
    snapshot = db.session.query(OperationRequestAsset).first()
    snapshot.target_data = {**snapshot.target_data, "location_id": True}
    flag_modified(snapshot, "target_data")
    db.session.commit()

    with pytest.raises(BusinessException):
        service.confirm(
            submitted["id"],
            _inspection_payload(context),
            context.manager.id,
        )


def test_different_actor_cannot_overwrite_confirmation_winner(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    grant_permissions(context.employee, "asset:usage:manage")
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    first_payload = _inspection_payload(context, key="first-winner")
    second_payload = {
        "return_location_id": context.location.id,
        "idempotency_key": "second-loser",
        "items": [
            {
                "asset_id": context.main_asset.id,
                "condition": "DAMAGED",
                "condition_description": "第二份验收",
            },
            {"asset_id": context.child_asset.id, "condition": "NORMAL"},
        ],
    }
    from app.services import operation_executor

    original_confirm = operation_executor.confirm
    interleaved = False
    second_results: list[dict[str, Any]] = []
    second_errors: list[BusinessException] = []

    def interleave_confirm(operation_request_id: int, actor_id: int):
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            try:
                second_results.append(
                    service.confirm(
                        operation_request_id,
                        second_payload,
                        context.employee.id,
                    )
                )
            except BusinessException as error:
                second_errors.append(error)
        return original_confirm(operation_request_id, actor_id)

    monkeypatch.setattr(operation_executor, "confirm", interleave_confirm)

    first = service.confirm(submitted["id"], first_payload, context.manager.id)

    assert second_results == []
    assert len(second_errors) == 1
    assert first["feature"]["return_location_id"] == context.return_location.id
    assert first["feature"]["items"] == [
        {
            "asset_id": context.main_asset.id,
            "condition": "NORMAL",
            "condition_description": None,
        },
        {
            "asset_id": context.child_asset.id,
            "condition": "DAMAGED",
            "condition_description": "外壳划痕",
        },
    ]
    detail = db.session.query(AssetReturnRequest).one()
    assert detail.return_location_id == context.return_location.id
    assert detail.confirmed_by == context.manager.id
    items = db.session.query(AssetReturnItem).order_by(AssetReturnItem.id.asc()).all()
    assert [item.condition for item in items] == ["NORMAL", "DAMAGED"]
    assert [asset.location_id for asset in _assets(context)] == [
        context.return_location.id,
        context.return_location.id,
    ]
    lifecycle = db.session.query(AssetLifecycleRecord).order_by(
        AssetLifecycleRecord.asset_id.asc()
    )
    assert [row.after_data["return_condition"] for row in lifecycle] == [
        "NORMAL",
        "DAMAGED",
    ]
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(OperationLog).count() == 1
    claims = db.session.query(OperationActionIdempotency).all()
    assert len(claims) == 1
    assert claims[0].actor_id == context.manager.id
    assert claims[0].idempotency_key == "first-winner"


@pytest.mark.parametrize(
    "invalid",
    [
        "before-approval",
        "non-manager",
        "missing",
        "extra",
        "duplicate",
        "invalid-condition",
        "blank-damage",
        "disabled-location",
    ],
)
def test_confirmation_rejects_invalid_input_without_partial_mutation(
    app,
    invalid: str,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    if invalid != "before-approval":
        _approve_personal(submitted, context.manager.id)
    payload = _inspection_payload(context)
    actor_id = context.manager.id
    if invalid == "non-manager":
        actor_id = context.employee.id
    elif invalid == "missing":
        payload["items"] = payload["items"][:-1]
    elif invalid == "extra":
        payload["items"].append({"asset_id": 999_999, "condition": "NORMAL"})
    elif invalid == "duplicate":
        payload["items"][1]["asset_id"] = context.main_asset.id
    elif invalid == "invalid-condition":
        payload["items"][0]["condition"] = "LOST"
    elif invalid == "blank-damage":
        payload["items"][1]["condition_description"] = "   "
    elif invalid == "disabled-location":
        context.return_location.status = RecordStatus.DISABLED.value
        db.session.commit()

    with pytest.raises(BusinessException):
        service.confirm(submitted["id"], payload, actor_id)

    detail = db.session.query(AssetReturnRequest).one()
    assert detail.return_location_id is None
    assert detail.confirmed_by is None
    assert detail.confirmed_at is None
    assert all(item.condition is None for item in db.session.query(AssetReturnItem))
    assert [asset.status for asset in _assets(context)] == [
        AssetStatus.IN_USE.value,
        AssetStatus.IN_USE.value,
    ]
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2


def test_confirmation_requires_scope_over_every_snapshot_organization(app) -> None:
    context = seed_usage_return_context()
    other = Organization(
        code="UR-RETURN-OTHER-ORG",
        name="UR Return Other Organization",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(other)
    db.session.flush()
    context.child_asset.organization_id = other.id
    _set_personal_in_use(context)
    _grant_self_return(context)
    manager_role = grant_permissions(context.manager, "asset:usage:manage")
    manager_role.data_scope = DataScope.DEPARTMENT.value
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)

    with pytest.raises(BusinessException, match="权限"):
        service.confirm(
            submitted["id"],
            _inspection_payload(context),
            context.manager.id,
        )

    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2


def test_processing_confirmation_claim_reports_in_progress(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    db.session.add(
        OperationActionIdempotency(
            operation_request_id=submitted["id"],
            actor_id=context.manager.id,
            action="RETURN_CONFIRM",
            idempotency_key="processing-confirm",
            status="PROCESSING",
        )
    )
    db.session.commit()

    with pytest.raises(BusinessException, match="处理中"):
        service.confirm(
            submitted["id"],
            _inspection_payload(context, key="processing-confirm"),
            context.manager.id,
        )

    assert db.session.query(OperationExecutionAttempt).count() == 0


def test_successful_confirmation_reconciles_processing_claim(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    completed = service.confirm(
        submitted["id"],
        _inspection_payload(context),
        context.manager.id,
    )
    assert completed["execution_status"] == ExecutionStatus.SUCCESS.value
    db.session.add(
        OperationActionIdempotency(
            operation_request_id=submitted["id"],
            actor_id=context.manager.id,
            action="RETURN_CONFIRM",
            idempotency_key="crashed-before-completed",
            status="PROCESSING",
        )
    )
    db.session.commit()

    replayed = service.confirm(
        submitted["id"],
        _inspection_payload(context, key="crashed-before-completed"),
        context.manager.id,
    )

    assert replayed["execution_status"] == ExecutionStatus.SUCCESS.value
    claim = db.session.query(OperationActionIdempotency).one()
    assert claim.status == "COMPLETED"
    assert db.session.query(OperationExecutionAttempt).count() == 1


def test_processing_claim_resumes_persisted_inspection_after_crash(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    from app.services import operation_executor

    original_confirm = operation_executor.confirm

    def crash_before_executor(operation_request_id: int, actor_id: int):
        raise RuntimeError("simulated crash before executor")

    monkeypatch.setattr(operation_executor, "confirm", crash_before_executor)
    with pytest.raises(RuntimeError, match="simulated crash"):
        service.confirm(
            submitted["id"],
            _inspection_payload(context, key="resume-after-crash"),
            context.manager.id,
        )
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
    assert db.session.query(OperationActionIdempotency).one().status == "PROCESSING"
    assert db.session.query(AssetReturnRequest).one().confirmed_by == context.manager.id
    assert db.session.query(OperationExecutionAttempt).count() == 0

    monkeypatch.setattr(operation_executor, "confirm", original_confirm)
    recovered = service.confirm(
        submitted["id"],
        _inspection_payload(context, key="resume-after-crash"),
        context.manager.id,
    )

    assert recovered["execution_status"] == ExecutionStatus.SUCCESS.value
    assert db.session.query(OperationActionIdempotency).one().status == "COMPLETED"
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1


def test_no_key_confirmation_resumes_matching_winner_after_crash(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    actor_id = context.manager.id
    return_location_id = context.return_location.id
    conflicting_location_id = context.location.id
    _approve_personal(submitted, actor_id)
    from app.services import operation_executor

    original_confirm = operation_executor.confirm

    def crash_before_executor(operation_request_id: int, actor_id: int):
        raise RuntimeError("simulated no-key crash")

    monkeypatch.setattr(operation_executor, "confirm", crash_before_executor)
    payload = _inspection_payload(context)
    with pytest.raises(RuntimeError, match="no-key crash"):
        service.confirm(submitted["id"], payload, actor_id)
    detail = db.session.query(AssetReturnRequest).one()
    assert detail.confirmed_by == actor_id
    assert db.session.query(OperationActionIdempotency).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2

    monkeypatch.setattr(operation_executor, "confirm", original_confirm)
    conflicting_payload = {
        "return_location_id": conflicting_location_id,
        "items": payload["items"],
    }
    with pytest.raises(BusinessException):
        service.confirm(
            submitted["id"],
            conflicting_payload,
            actor_id,
        )
    assert db.session.query(OperationExecutionAttempt).count() == 0

    recovered = service.confirm(submitted["id"], payload, actor_id)

    assert recovered["execution_status"] == ExecutionStatus.SUCCESS.value
    assert recovered["feature"]["return_location_id"] == return_location_id
    assert db.session.query(OperationActionIdempotency).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 0


def test_failed_no_key_confirmation_replay_does_not_retry(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    context.child_asset.version += 1
    db.session.commit()
    payload = _inspection_payload(context)
    failed = service.confirm(submitted["id"], payload, context.manager.id)
    assert failed["execution_status"] == ExecutionStatus.FAILED.value

    replayed = service.confirm(submitted["id"], payload, context.manager.id)

    assert replayed["execution_status"] == ExecutionStatus.FAILED.value
    assert db.session.query(OperationExecutionAttempt).count() == 1


@pytest.mark.parametrize("pending_kind", ["new", "dirty", "deleted"])
def test_confirm_rejects_pending_unit_of_work_before_any_query(
    app,
    monkeypatch,
    pending_kind: str,
) -> None:
    context = seed_usage_return_context()
    sentinel = Organization(
        code=f"UR-CONFIRM-SENTINEL-{pending_kind}",
        name=f"UR Confirm Sentinel {pending_kind}",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(sentinel)
    db.session.commit()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    actor_id = context.manager.id
    _approve_personal(submitted, actor_id)
    from app.services import operation_executor

    original_confirm = operation_executor.confirm

    def crash_before_executor(operation_request_id: int, actor_id: int):
        raise RuntimeError("simulated pending-uow confirm crash")

    monkeypatch.setattr(operation_executor, "confirm", crash_before_executor)
    payload = _inspection_payload(context, key=f"pending-confirm-{pending_kind}")
    with pytest.raises(RuntimeError, match="pending-uow"):
        service.confirm(submitted["id"], payload, actor_id)
    monkeypatch.setattr(operation_executor, "confirm", original_confirm)
    pending = _stage_pending_organization(
        pending_kind,
        sentinel,
        f"CONFIRM-{pending_kind}",
    )
    statements: list[str] = []
    engine = db.engine

    def record_statement(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        with pytest.raises(RuntimeError, match="pending business writes"):
            service.confirm(submitted["id"], payload, actor_id)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert statements == []
    _assert_pending_organization_survives(pending_kind, pending)


@pytest.mark.parametrize(
    "terminal_status",
    [ExecutionStatus.SUCCESS.value, ExecutionStatus.FAILED.value],
)
def test_processing_recovery_refreshes_stale_operation_before_executor(
    tmp_path,
    monkeypatch,
    terminal_status: str,
) -> None:
    database = tmp_path / f"return-stale-{terminal_status.lower()}.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _set_personal_in_use(context)
        _grant_self_return(context)
        _grant_return_manage(context)
        operation_handler_registry.clear()
        register_usage_return_handlers()
        service = _return_service()
        submitted = service.submit_personal(
            _personal_payload(context),
            context.employee.id,
        )
        _approve_personal(submitted, context.manager.id)
        from app.services import operation_executor

        original_confirm = operation_executor.confirm

        def crash_before_executor(operation_request_id: int, actor_id: int):
            raise RuntimeError("simulated stale recovery crash")

        monkeypatch.setattr(operation_executor, "confirm", crash_before_executor)
        with pytest.raises(RuntimeError, match="stale recovery"):
            service.confirm(
                submitted["id"],
                _inspection_payload(context, key="stale-recovery"),
                context.manager.id,
            )
        cached_operation = db.session.get(OperationRequest, submitted["id"])
        assert cached_operation is not None
        assert cached_operation.execution_status == ExecutionStatus.NOT_STARTED.value
        operation_id = submitted["id"]
        actor_id = context.manager.id
        child_asset_id = context.child_asset.id
        monkeypatch.setattr(operation_executor, "confirm", original_confirm)

        def settle_in_other_session() -> str:
            with concurrent_app.app_context():
                if terminal_status == ExecutionStatus.FAILED.value:
                    child = db.session.get(Asset, child_asset_id)
                    assert child is not None
                    child.version += 1
                    db.session.commit()
                settled = operation_executor.confirm(operation_id, actor_id)
                result = settled.execution_status
                db.session.remove()
                return result

        with ThreadPoolExecutor(max_workers=1) as executor:
            settled_status = executor.submit(settle_in_other_session).result(timeout=5)
        assert settled_status == terminal_status
        assert cached_operation.execution_status == ExecutionStatus.NOT_STARTED.value

        recovered = service.confirm(
            operation_id,
            _inspection_payload(context, key="stale-recovery"),
            actor_id,
        )

        assert recovered["execution_status"] == terminal_status
        assert db.session.query(OperationExecutionAttempt).count() == 1
        assert db.session.query(OperationActionIdempotency).one().status == "COMPLETED"
        if terminal_status == ExecutionStatus.SUCCESS.value:
            assert db.session.query(AssetLifecycleRecord).count() == 2
            assert db.session.query(OperationLog).count() == 1
            assert db.session.query(AssetBusinessLock).count() == 0
        else:
            assert db.session.query(AssetLifecycleRecord).count() == 0
            assert db.session.query(OperationLog).count() == 0
            assert db.session.query(AssetBusinessLock).count() == 2
        db.session.remove()
        db.drop_all()


def test_failed_confirmation_reconciles_processing_claim(app) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    context.child_asset.version += 1
    db.session.commit()
    failed = service.confirm(
        submitted["id"],
        _inspection_payload(context),
        context.manager.id,
    )
    assert failed["execution_status"] == ExecutionStatus.FAILED.value
    db.session.add(
        OperationActionIdempotency(
            operation_request_id=submitted["id"],
            actor_id=context.manager.id,
            action="RETURN_CONFIRM",
            idempotency_key="failed-before-completed",
            status="PROCESSING",
        )
    )
    db.session.commit()

    replayed = service.confirm(
        submitted["id"],
        _inspection_payload(context, key="failed-before-completed"),
        context.manager.id,
    )

    assert replayed["execution_status"] == ExecutionStatus.FAILED.value
    assert db.session.query(OperationActionIdempotency).one().status == "COMPLETED"
    assert db.session.query(OperationExecutionAttempt).count() == 1


def test_failed_confirmation_with_new_key_rejects_before_claim(
    app, monkeypatch
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    context.child_asset.version += 1
    db.session.commit()
    failed = service.confirm(
        submitted["id"],
        _inspection_payload(context),
        context.manager.id,
    )
    assert failed["execution_status"] == ExecutionStatus.FAILED.value

    from app.repositories.operation_repository import (
        operation_action_idempotency_repository,
    )

    add_calls = 0
    original_add = operation_action_idempotency_repository.add

    def record_add(entity: OperationActionIdempotency) -> OperationActionIdempotency:
        nonlocal add_calls
        add_calls += 1
        return original_add(entity)

    monkeypatch.setattr(operation_action_idempotency_repository, "add", record_add)

    with pytest.raises(BusinessException, match="其他验收请求"):
        service.confirm(
            submitted["id"],
            _inspection_payload(context, key="new-key-after-failure"),
            context.manager.id,
        )

    assert add_calls == 0
    assert db.session.query(OperationActionIdempotency).count() == 0


@pytest.mark.parametrize("failure", ["version", "location"])
def test_confirmation_execution_failure_retains_inspection_and_locks(
    app,
    monkeypatch,
    failure: str,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    if failure == "version":
        context.child_asset.version += 1
        db.session.commit()
    else:
        from app.services import operation_executor

        original_confirm = operation_executor.confirm

        def disable_then_confirm(operation_request_id: int, actor_id: int):
            location = db.session.get(
                type(context.return_location), context.return_location.id
            )
            assert location is not None
            location.status = RecordStatus.DISABLED.value
            db.session.commit()
            return original_confirm(operation_request_id, actor_id)

        monkeypatch.setattr(operation_executor, "confirm", disable_then_confirm)

    result = service.confirm(
        submitted["id"],
        _inspection_payload(context, key=f"failed-{failure}"),
        context.manager.id,
    )

    assert result["execution_status"] == ExecutionStatus.FAILED.value
    detail = db.session.query(AssetReturnRequest).one()
    assert detail.return_location_id == context.return_location.id
    assert detail.confirmed_by == context.manager.id
    assert detail.confirmed_at is not None
    items = db.session.query(AssetReturnItem).order_by(AssetReturnItem.id.asc()).all()
    assert [item.condition for item in items] == ["NORMAL", "DAMAGED"]
    assert items[1].condition_description == "外壳划痕"
    assert db.session.query(OperationExecutionAttempt).one().status == "FAILED"
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2
    assert db.session.query(OperationActionIdempotency).one().status == "COMPLETED"

    replayed = service.confirm(
        submitted["id"],
        _inspection_payload(context, key=f"failed-{failure}"),
        context.manager.id,
    )
    assert replayed["execution_status"] == ExecutionStatus.FAILED.value
    assert db.session.query(OperationExecutionAttempt).count() == 1


def test_terminated_confirmation_replays_settle_processing_claim(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    actor_id = context.manager.id
    operation_id = submitted["id"]
    _approve_personal(submitted, actor_id)
    keyed_payload = _inspection_payload(context, key="terminated-confirmation")
    no_key_payload = _inspection_payload(context)
    new_key_payload = _inspection_payload(context, key="terminated-new-key")
    context.child_asset.version += 1
    db.session.commit()
    original_complete = service._complete_confirmation_action

    def crash_before_action_completion(
        operation_request_id: int,
        completed_by: int,
        idempotency_key: str,
    ) -> None:
        raise RuntimeError("crash before confirmation action completion")

    monkeypatch.setattr(
        service,
        "_complete_confirmation_action",
        crash_before_action_completion,
    )
    with pytest.raises(RuntimeError, match="action completion"):
        service.confirm(operation_id, keyed_payload, actor_id)
    monkeypatch.setattr(
        service,
        "_complete_confirmation_action",
        original_complete,
    )

    failed = db.session.get(OperationRequest, operation_id)
    assert failed is not None
    assert failed.execution_status == ExecutionStatus.FAILED.value
    claim = db.session.query(OperationActionIdempotency).one()
    assert claim.status == "PROCESSING"
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 2

    from app.services import operation_executor

    terminated = operation_executor.terminate(
        operation_id,
        actor_id,
        "验收失败后终止",
    )
    assert terminated.execution_status == ExecutionStatus.TERMINATED.value
    assert db.session.query(AssetBusinessLock).count() == 0

    results: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for replay_kind, payload in (
        ("no_key", no_key_payload),
        ("keyed", keyed_payload),
    ):
        try:
            results[replay_kind] = service.confirm(operation_id, payload, actor_id)
        except BusinessException as error:
            errors[replay_kind] = error.message

    assert errors == {}
    assert results["no_key"]["execution_status"] == ExecutionStatus.TERMINATED.value
    assert results["keyed"]["execution_status"] == ExecutionStatus.TERMINATED.value
    with pytest.raises(BusinessException, match="其他验收请求"):
        service.confirm(operation_id, new_key_payload, actor_id)
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 0
    claim = db.session.query(OperationActionIdempotency).one()
    assert claim.status == "COMPLETED"


@pytest.mark.parametrize(
    "tamper",
    [
        "asset-before",
        "return-location-snapshot",
        "confirmed-by-snapshot",
    ],
)
def test_generic_retry_rejects_tampered_persisted_snapshot(
    app,
    monkeypatch,
    tamper: str,
) -> None:
    context = seed_usage_return_context()
    _set_personal_in_use(context)
    _grant_self_return(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.employee.id,
    )
    _approve_personal(submitted, context.manager.id)
    from app.services import operation_executor

    original_confirm = operation_executor.confirm

    def disable_then_confirm(operation_request_id: int, actor_id: int):
        context.return_location.status = RecordStatus.DISABLED.value
        db.session.commit()
        return original_confirm(operation_request_id, actor_id)

    monkeypatch.setattr(operation_executor, "confirm", disable_then_confirm)
    failed = service.confirm(
        submitted["id"],
        _inspection_payload(context),
        context.manager.id,
    )
    assert failed["execution_status"] == ExecutionStatus.FAILED.value
    context.return_location.status = RecordStatus.ENABLED.value
    if tamper == "asset-before":
        snapshot = db.session.query(OperationRequestAsset).first()
        snapshot.before_data = {
            **snapshot.before_data,
            "public_object_name": "FORGED",
            "unexpected": True,
        }
        flag_modified(snapshot, "before_data")
    else:
        detail = db.session.query(AssetReturnRequest).one()
        if tamper == "return-location-snapshot":
            detail.return_location_snapshot = {
                **detail.return_location_snapshot,
                "id": context.location.id,
            }
        else:
            detail.confirmed_by_snapshot = {
                **detail.confirmed_by_snapshot,
                "id": context.employee.id,
            }
    db.session.commit()

    retried = operation_executor.retry(submitted["id"], context.manager.id)

    assert retried.execution_status == ExecutionStatus.FAILED.value
    assert db.session.query(OperationExecutionAttempt).count() == 2
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2


def test_public_return_accepts_different_public_objects_and_executes_directly(
    app,
) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    other_public_object = PublicUsageObject(
        code="UR-SECOND-PUBLIC-OBJECT",
        name="UR Second Public Object",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(other_public_object)
    db.session.flush()
    context.child_asset.public_object_id = other_public_object.id
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()

    result = _return_service().submit_public(
        {
            "asset_ids": [context.main_asset.id],
            **_inspection_payload(context),
            "idempotency_key": "public-return-once",
        },
        context.manager.id,
    )

    assert result["operation_type"] == OperationType.PUBLIC_RETURN.value
    assert result["approval_channel"] == ApprovalChannel.DIRECT.value
    assert result["approval_execution_mode"] == (
        ApprovalExecutionMode.AUTO_ON_APPROVAL.value
    )
    assert result["approval_status"] == ApprovalStatus.APPROVED.value
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert result["feature"]["confirmed_by"] == context.manager.id
    assert len(result["feature"]["items"]) == 2
    for asset in _assets(context):
        assert asset.status == AssetStatus.IDLE.value
        assert asset.usage_type is None
        assert asset.holder_user_id is None
        assert asset.public_object_id is None
        assert asset.usage_department_id is None
        assert asset.location_id == context.return_location.id
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 0

    replayed = _return_service().submit_public(
        {
            "asset_ids": [999_999],
            "return_location_id": -1,
            "items": [{"asset_id": -1, "condition": "LOST"}],
            "idempotency_key": "public-return-once",
        },
        context.manager.id,
    )
    assert replayed == result
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 1


def test_public_return_snapshots_survive_master_data_changes(app) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)
    grant_permissions(context.employee, "asset:usage:manage")
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    employee_id = context.employee.id
    manager_id = context.manager.id
    payload = {
        "asset_ids": [context.main_asset.id],
        **_inspection_payload(context),
        "idempotency_key": "public-return-historical-snapshots",
    }
    expected_location = {
        "id": context.return_location.id,
        "code": context.return_location.code,
        "name": context.return_location.name,
    }
    expected_confirmer = {
        "id": context.manager.id,
        "username": context.manager.username,
        "name": context.manager.nickname,
    }
    first = service.submit_public(payload, manager_id)
    context.return_location.name = "UR Public Return Location Renamed"
    context.return_location.status = RecordStatus.DISABLED.value
    context.manager.username = "UR-public-manager-renamed"
    context.manager.nickname = "UR Public Manager Renamed"
    db.session.commit()

    replayed = service.submit_public(payload, manager_id)
    manager = db.session.get(User, manager_id)
    assert manager is not None
    manager.enabled = False
    db.session.commit()
    detail = service.get(first["id"], employee_id)
    page_item = service.page(
        actor_id=employee_id,
        page_index=0,
        size=10,
    ).items[0]

    for item in (first, replayed, detail, page_item):
        feature = item["feature"]
        assert feature.get("return_location_snapshot") == expected_location
        assert feature.get("confirmed_by_snapshot") == expected_confirmer


def test_public_return_replay_resumes_after_direct_approval_crash(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    from app.services import operation_executor

    original_execute = operation_executor.execute_after_approval

    def crash_after_direct_approval(operation_request_id: int, actor_id: int):
        raise RuntimeError("simulated crash after direct approval")

    monkeypatch.setattr(
        operation_executor,
        "execute_after_approval",
        crash_after_direct_approval,
    )
    with pytest.raises(RuntimeError, match="after direct approval"):
        service.submit_public(
            {
                "asset_ids": [context.main_asset.id],
                **_inspection_payload(context),
                "idempotency_key": "public-direct-crash",
            },
            context.manager.id,
        )
    operation = db.session.query(OperationRequest).one()
    assert operation.approval_status == ApprovalStatus.APPROVED.value
    assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 2

    monkeypatch.setattr(
        operation_executor,
        "execute_after_approval",
        original_execute,
    )
    recovered = service.submit_public(
        {
            "asset_ids": [999_999],
            "return_location_id": -1,
            "items": [{"asset_id": -1, "condition": "LOST"}],
            "idempotency_key": "public-direct-crash",
        },
        context.manager.id,
    )

    assert recovered["execution_status"] == ExecutionStatus.SUCCESS.value
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 0


def test_public_created_false_path_resumes_approved_not_started(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    from app.services import operation_executor, operation_service

    original_execute = operation_executor.execute_after_approval

    def crash_after_direct_approval(operation_request_id: int, actor_id: int):
        raise RuntimeError("simulated created-false crash")

    monkeypatch.setattr(
        operation_executor,
        "execute_after_approval",
        crash_after_direct_approval,
    )
    payload = {
        "asset_ids": [context.main_asset.id],
        **_inspection_payload(context),
        "idempotency_key": "public-created-false",
    }
    with pytest.raises(RuntimeError, match="created-false"):
        service.submit_public(payload, context.manager.id)
    operation = db.session.query(OperationRequest).one()
    assert operation.approval_status == ApprovalStatus.APPROVED.value
    assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
    monkeypatch.setattr(
        operation_executor,
        "execute_after_approval",
        original_execute,
    )
    original_lookup = operation_service.get_by_idempotency_key
    lookup_calls = 0

    def miss_early_lookup(actor_id: int, operation_type: str, key: str):
        nonlocal lookup_calls
        lookup_calls += 1
        if lookup_calls == 1:
            return None
        return original_lookup(actor_id, operation_type, key)

    monkeypatch.setattr(
        operation_service,
        "get_by_idempotency_key",
        miss_early_lookup,
    )

    recovered = service.submit_public(payload, context.manager.id)

    assert lookup_calls >= 2
    assert recovered["execution_status"] == ExecutionStatus.SUCCESS.value
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 0


@pytest.mark.parametrize("pending_kind", ["new", "dirty", "deleted"])
def test_submit_public_rejects_pending_unit_of_work_before_any_query(
    app,
    monkeypatch,
    pending_kind: str,
) -> None:
    context = seed_usage_return_context()
    sentinel = Organization(
        code=f"UR-PUBLIC-SENTINEL-{pending_kind}",
        name=f"UR Public Sentinel {pending_kind}",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(sentinel)
    db.session.commit()
    _set_public_in_use(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    from app.services import operation_executor

    original_execute = operation_executor.execute_after_approval

    def crash_after_direct_approval(operation_request_id: int, actor_id: int):
        raise RuntimeError("simulated pending-uow public crash")

    monkeypatch.setattr(
        operation_executor,
        "execute_after_approval",
        crash_after_direct_approval,
    )
    payload = {
        "asset_ids": [context.main_asset.id],
        **_inspection_payload(context),
        "idempotency_key": f"pending-public-{pending_kind}",
    }
    actor_id = context.manager.id
    with pytest.raises(RuntimeError, match="pending-uow"):
        service.submit_public(payload, actor_id)
    monkeypatch.setattr(
        operation_executor,
        "execute_after_approval",
        original_execute,
    )
    pending = _stage_pending_organization(
        pending_kind,
        sentinel,
        f"PUBLIC-{pending_kind}",
    )
    statements: list[str] = []
    engine = db.engine

    def record_statement(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        with pytest.raises(RuntimeError, match="pending business writes"):
            service.submit_public(payload, actor_id)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert statements == []
    _assert_pending_organization_survives(pending_kind, pending)


@pytest.mark.parametrize(
    "corruption",
    ["operation", "detail", "item", "snapshot", "boolean-target"],
)
def test_public_return_replay_rejects_aggregate_contradictions(
    app,
    corruption: str,
) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    service = _return_service()
    service.submit_public(
        {
            "asset_ids": [context.main_asset.id],
            **_inspection_payload(context),
            "idempotency_key": f"public-corrupt-{corruption}",
        },
        context.manager.id,
    )
    if corruption == "operation":
        db.session.query(
            OperationRequest
        ).one().approval_channel = ApprovalChannel.FEISHU.value
    elif corruption == "detail":
        db.session.query(
            AssetReturnRequest
        ).one().return_location_id = context.location.id
    elif corruption == "item":
        item = db.session.query(AssetReturnItem).first()
        item.condition = "NORMAL"
        item.condition_description = "不应保留"
    else:
        snapshot = db.session.query(OperationRequestAsset).first()
        if corruption == "snapshot":
            snapshot.before_data = {**snapshot.before_data, "version": 99}
            flag_modified(snapshot, "before_data")
        else:
            snapshot.target_data = {**snapshot.target_data, "location_id": True}
            flag_modified(snapshot, "target_data")
    db.session.commit()

    with pytest.raises(BusinessException):
        service.submit_public(
            {
                "asset_ids": [999_999],
                "return_location_id": -1,
                "items": [{"asset_id": -1, "condition": "LOST"}],
                "idempotency_key": f"public-corrupt-{corruption}",
            },
            context.manager.id,
        )

    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 1


def test_public_return_rejects_boolean_ids_before_creating_request(app) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)

    with pytest.raises(BusinessException):
        _return_service().submit_public(
            {
                "asset_ids": [True],
                "return_location_id": True,
                "items": [{"asset_id": True, "condition": "NORMAL"}],
            },
            context.manager.id,
        )

    _assert_no_return_aggregate()


def test_public_return_checks_complete_items_before_return_location(app) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)

    with pytest.raises(BusinessException, match="验收资产必须与申请资产完全一致"):
        _return_service().submit_public(
            {
                "asset_ids": [context.main_asset.id],
                "return_location_id": 999_999,
                "items": [{"asset_id": context.main_asset.id, "condition": "NORMAL"}],
            },
            context.manager.id,
        )

    _assert_no_return_aggregate()


@pytest.mark.parametrize("invalid", ["personal", "mixed", "incomplete"])
def test_public_return_rejects_invalid_assets_or_inspections_without_writes(
    app,
    invalid: str,
) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)
    payload = {
        "asset_ids": [context.main_asset.id],
        **_inspection_payload(context),
    }
    if invalid == "personal":
        _set_personal_in_use(context)
    elif invalid == "mixed":
        context.child_asset.usage_type = UsageType.PERSONAL.value
        context.child_asset.public_object_id = None
        context.child_asset.holder_user_id = context.employee.id
        db.session.commit()
    else:
        payload["items"] = payload["items"][:-1]

    with pytest.raises(BusinessException):
        _return_service().submit_public(payload, context.manager.id)

    _assert_no_return_aggregate()


def test_return_handler_never_passes_inspection_metadata_to_asset_cas(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _set_public_in_use(context)
    _grant_return_manage(context)
    operation_handler_registry.clear()
    register_usage_return_handlers()
    from app.repositories.asset_repository import asset_repository

    original = asset_repository.cas_update
    changes_seen: list[set[str]] = []

    def recording_cas(
        asset_id: int,
        expected_version: int,
        changes: dict[str, object],
    ) -> bool:
        changes_seen.append(set(changes))
        return original(asset_id, expected_version, changes)

    monkeypatch.setattr(asset_repository, "cas_update", recording_cas)

    _return_service().submit_public(
        {
            "asset_ids": [context.main_asset.id],
            **_inspection_payload(context),
        },
        context.manager.id,
    )

    assert changes_seen == [
        {
            "status",
            "usage_type",
            "holder_user_id",
            "public_object_id",
            "usage_department_id",
            "location_id",
        },
        {
            "status",
            "usage_type",
            "holder_user_id",
            "public_object_id",
            "usage_department_id",
            "location_id",
        },
    ]
