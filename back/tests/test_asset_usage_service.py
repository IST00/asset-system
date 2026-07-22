"""Personal and public asset-usage service and handler contracts."""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

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
    ExternalApprovalEvent,
    OperationExecutionAttempt,
    OperationLog,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    PublicUsageObject,
    User,
)
from app.models.asset_usage_return import AssetUsageRequest
from app.operations.registry import operation_handler_registry
from app.repositories.asset_repository import asset_repository
from app.services import (
    approval_provider_service,
    operation_service,
    permission_service,
)
from app.services.asset_usage_return_support import serialize_operation
from asset_usage_return_fixtures import (
    UsageReturnContext,
    grant_permissions,
    grant_scoped_manager_permission,
    seed_cross_scope_usage,
    seed_usage_return_context,
)


def _usage_service() -> ModuleType:
    try:
        return importlib.import_module("app.services.asset_usage_service")
    except ModuleNotFoundError as error:
        raise AssertionError("missing asset_usage_service") from error


def _handler_module() -> ModuleType:
    try:
        return importlib.import_module("app.operations.asset_usage_return_handlers")
    except ModuleNotFoundError as error:
        raise AssertionError("missing asset usage handlers") from error


def _register_usage_handlers() -> ModuleType:
    module = _handler_module()
    operation_handler_registry.clear()
    operation_handler_registry.register(module.PersonalUsageHandler())
    operation_handler_registry.register(module.PublicUsageHandler())
    return module


def _grant_usage(context: UsageReturnContext) -> None:
    grant_permissions(context.manager, "asset:usage:manage")


def _personal_payload(
    context: UsageReturnContext,
    *,
    key: str | None = None,
    location_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "asset_ids": [context.main_asset.id],
        "target_user_id": context.employee.id,
    }
    if key is not None:
        payload["idempotency_key"] = key
    if location_id is not None:
        payload["location_id"] = location_id
    return payload


def _public_payload(
    context: UsageReturnContext,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "asset_ids": [context.main_asset.id],
        "public_object_id": context.public_object.id,
        "location_id": context.return_location.id,
    }
    if key is not None:
        payload["idempotency_key"] = key
    return payload


def _create_pending_public_usage(
    context: UsageReturnContext,
    *,
    idempotency_key: str | None = None,
) -> OperationRequest:
    target = {
        "status": AssetStatus.IN_USE.value,
        "usage_type": UsageType.PUBLIC.value,
        "holder_user_id": None,
        "public_object_id": context.public_object.id,
        "usage_department_id": None,
        "location_id": context.return_location.id,
    }
    operation = operation_service.create_request(
        operation_type=OperationType.PUBLIC_USE.value,
        applicant_id=context.manager.id,
        approval_channel=ApprovalChannel.DIRECT.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=[context.main_asset, context.child_asset],
        target_data_by_asset_id={
            context.main_asset.id: target,
            context.child_asset.id: target,
        },
        idempotency_key=idempotency_key,
    ).operation
    db.session.add(
        AssetUsageRequest(
            operation_request_id=operation.id,
            target_user_id=None,
            target_public_object_id=context.public_object.id,
            usage_department_id=None,
            target_location_id=context.return_location.id,
        )
    )
    db.session.commit()
    return operation


def _seed_personal_usage_request(
    context: UsageReturnContext,
    asset: Asset,
    *,
    applicant_id: int,
) -> OperationRequest:
    target = {
        "status": AssetStatus.IN_USE.value,
        "usage_type": UsageType.PERSONAL.value,
        "holder_user_id": context.manager.id,
        "public_object_id": None,
        "usage_department_id": context.organization.id,
        "location_id": asset.location_id,
    }
    operation = operation_service.create_request(
        operation_type=OperationType.PERSONAL_USE.value,
        applicant_id=applicant_id,
        approval_channel=ApprovalChannel.FEISHU.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=[asset],
        target_data_by_asset_id={asset.id: target},
        idempotency_key=None,
    ).operation
    db.session.add(
        AssetUsageRequest(
            operation_request_id=operation.id,
            target_user_id=context.manager.id,
            target_public_object_id=None,
            usage_department_id=context.organization.id,
            target_location_id=None,
        )
    )
    db.session.flush()
    operation_service.release_locks(operation.id)
    return operation


def _assert_no_usage_request_data() -> None:
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(OperationRequestAsset).count() == 0
    assert db.session.query(AssetUsageRequest).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 0


def _assets(context: UsageReturnContext) -> list[Asset]:
    db.session.expire_all()
    result = [
        db.session.get(Asset, context.main_asset.id),
        db.session.get(Asset, context.child_asset.id),
    ]
    assert all(asset is not None for asset in result)
    return [asset for asset in result if asset is not None]


def test_personal_usage_target_can_view_detail_without_manage_permission(app) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    submitted = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )

    detail = _usage_service().get(submitted["id"], context.employee.id)
    result = _usage_service().page(
        actor_id=context.employee.id,
        page_index=0,
        size=10,
    )

    assert detail == submitted
    assert result.total == 1
    assert result.items == [detail]


def test_usage_applicant_can_view_own_detail_and_page(app) -> None:
    seeded = seed_cross_scope_usage()
    db.session.commit()
    service = _usage_service()

    detail = service.get(seeded.operation.id, seeded.applicant.id)
    result = service.page(
        actor_id=seeded.applicant.id,
        page_index=0,
        size=10,
    )

    assert detail["id"] == seeded.operation.id
    assert result.total == 1
    assert [item["id"] for item in result.items] == [seeded.operation.id]


def test_usage_manager_visibility_requires_scope_over_every_snapshot(app) -> None:
    seeded = seed_cross_scope_usage()
    grant_scoped_manager_permission(
        seeded.base.manager,
        seeded.base.organization.id,
    )
    db.session.commit()
    service = _usage_service()

    with pytest.raises(BusinessException, match="无权查看"):
        service.get(seeded.operation.id, seeded.base.manager.id)
    partial_page = service.page(
        actor_id=seeded.base.manager.id,
        page_index=0,
        size=10,
    )

    assert partial_page.total == 0

    grant_scoped_manager_permission(
        seeded.base.manager,
        seeded.other_organization.id,
    )
    db.session.commit()

    detail = service.get(seeded.operation.id, seeded.base.manager.id)
    full_page = service.page(
        actor_id=seeded.base.manager.id,
        page_index=0,
        size=10,
    )

    assert detail["id"] == seeded.operation.id
    assert len(detail["assets"]) == 2
    assert full_page.total == 1
    assert [item["id"] for item in full_page.items] == [seeded.operation.id]


def test_usage_limited_scope_manager_cannot_view_request_without_snapshots(app) -> None:
    seeded = seed_cross_scope_usage()
    grant_scoped_manager_permission(
        seeded.base.manager,
        seeded.base.organization.id,
    )
    db.session.query(OperationRequestAsset).filter(
        OperationRequestAsset.operation_request_id == seeded.operation.id
    ).delete(synchronize_session=False)
    db.session.commit()
    service = _usage_service()

    with pytest.raises(BusinessException, match="无权查看"):
        service.get(seeded.operation.id, seeded.base.manager.id)

    result = service.page(
        actor_id=seeded.base.manager.id,
        page_index=0,
        size=10,
    )

    assert result.total == 0
    assert result.items == []


def test_usage_page_is_newest_first_with_stable_id_tiebreak_and_exact_total(
    app,
) -> None:
    context = seed_usage_return_context()
    first = _seed_personal_usage_request(
        context,
        context.main_asset,
        applicant_id=context.employee.id,
    )
    second = _seed_personal_usage_request(
        context,
        context.child_asset,
        applicant_id=context.employee.id,
    )
    third = _seed_personal_usage_request(
        context,
        context.main_asset,
        applicant_id=context.employee.id,
    )
    same_created_at = datetime(2026, 7, 22, 1, 2, 3, tzinfo=timezone.utc)
    first.created_at = same_created_at
    second.created_at = same_created_at
    third.created_at = datetime(2026, 7, 21, 1, 2, 3, tzinfo=timezone.utc)
    db.session.commit()
    service = _usage_service()

    newest_page = service.page(
        actor_id=context.employee.id,
        page_index=0,
        size=1,
    )
    older_page = service.page(
        actor_id=context.employee.id,
        page_index=1,
        size=1,
    )
    oldest_page = service.page(
        actor_id=context.employee.id,
        page_index=2,
        size=1,
    )

    assert newest_page.total == 3
    assert newest_page.page == 0
    assert newest_page.size == 1
    assert [item["id"] for item in newest_page.items] == [second.id]
    assert older_page.total == 3
    assert older_page.page == 1
    assert older_page.size == 1
    assert [item["id"] for item in older_page.items] == [first.id]
    assert oldest_page.total == 3
    assert [item["id"] for item in oldest_page.items] == [third.id]


def test_usage_page_query_count_is_constant_when_page_size_grows(app) -> None:
    context = seed_usage_return_context()
    for _index in range(5):
        _seed_personal_usage_request(
            context,
            context.main_asset,
            applicant_id=context.employee.id,
        )
    db.session.commit()
    actor_id = context.employee.id
    service = _usage_service()
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


def test_shared_serializer_preloaded_assets_match_default_without_permission_query(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    operation = _seed_personal_usage_request(
        context,
        context.main_asset,
        applicant_id=context.employee.id,
    )
    db.session.commit()
    snapshots = (
        db.session.query(OperationRequestAsset)
        .filter(OperationRequestAsset.operation_request_id == operation.id)
        .order_by(OperationRequestAsset.asset_id.asc())
        .all()
    )
    default_result = serialize_operation(operation, context.employee.id)

    def reject_permission_query(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("pre-resolved False must not query amount permission")

    monkeypatch.setattr(permission_service, "has_permission", reject_permission_query)

    preloaded_result = serialize_operation(
        operation,
        context.employee.id,
        assets=snapshots,
        can_view_amount=False,
    )

    assert preloaded_result == default_result
    preloaded_result["assets"][0]["before_data"]["status"] = "MUTATED"
    assert snapshots[0].before_data["status"] != "MUTATED"


def test_usage_page_preloaded_rows_still_run_strict_snapshot_validation(app) -> None:
    context = seed_usage_return_context()
    operation = _seed_personal_usage_request(
        context,
        context.main_asset,
        applicant_id=context.employee.id,
    )
    snapshot = (
        db.session.query(OperationRequestAsset)
        .filter(OperationRequestAsset.operation_request_id == operation.id)
        .one()
    )
    snapshot.target_data = {**snapshot.target_data, "unexpected": True}
    flag_modified(snapshot, "target_data")
    db.session.commit()

    with pytest.raises(BusinessException, match="不匹配"):
        _usage_service().page(
            actor_id=context.employee.id,
            page_index=0,
            size=10,
        )


def test_usage_query_recursively_filters_amount_keys_present_in_snapshot_json(
    app,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    service = _usage_service()
    submitted = service.submit_personal(
        _personal_payload(context),
        context.manager.id,
    )
    snapshot = (
        db.session.query(OperationRequestAsset)
        .filter(OperationRequestAsset.asset_id == context.main_asset.id)
        .one()
    )
    original_asset_name = snapshot.asset_name_snapshot
    original_location_name = snapshot.location_snapshot["name"]
    snapshot.before_data = {
        **snapshot.before_data,
        "original_amount": "100.00",
        "nested": {"repair_cost": "5.00", "safe": "kept"},
    }
    context.main_asset.asset_name = "UR Current Renamed Asset"
    context.employee.nickname = "UR Current Renamed Employee"
    context.employee.enabled = False
    context.location.name = "UR Current Renamed Location"
    context.location.status = RecordStatus.DISABLED.value
    db.session.commit()

    detail = service.get(submitted["id"], context.manager.id)
    result = service.page(
        actor_id=context.manager.id,
        page_index=0,
        size=10,
    )

    assert set(detail) == {
        "id",
        "request_no",
        "operation_type",
        "applicant_id",
        "approval_channel",
        "approval_execution_mode",
        "approval_status",
        "execution_status",
        "execution_error",
        "external_instance_id",
        "submitted_at",
        "approved_at",
        "executed_at",
        "terminated_at",
        "terminated_by",
        "termination_reason",
        "created_at",
        "updated_at",
        "assets",
        "feature",
        "allowed_actions",
    }
    assert result.items == [detail]
    asset_detail = next(
        item for item in detail["assets"] if item["asset_id"] == context.main_asset.id
    )
    assert asset_detail["asset_name"] == original_asset_name
    assert asset_detail["location_snapshot"]["name"] == original_location_name
    assert asset_detail["before_data"]["nested"] == {"safe": "kept"}
    assert "original_amount" not in asset_detail["before_data"]
    assert detail["feature"]["target_user_id"] == context.employee.id
    assert detail["allowed_actions"] == []

    grant_permissions(context.manager, "asset:amount:view")
    db.session.commit()

    amount_detail = service.get(submitted["id"], context.manager.id)
    amount_asset = next(
        item
        for item in amount_detail["assets"]
        if item["asset_id"] == context.main_asset.id
    )

    assert amount_asset["before_data"]["original_amount"] == "100.00"
    assert amount_asset["before_data"]["nested"]["repair_cost"] == "5.00"


def _assert_failed_without_asset_updates(
    context: UsageReturnContext,
    operation_request_id: int,
    safe_error_message: str,
) -> None:
    db.session.expire_all()
    operation = db.session.get(OperationRequest, operation_request_id)
    assert operation is not None
    assert operation.approval_status == ApprovalStatus.APPROVED.value
    assert operation.execution_status == ExecutionStatus.FAILED.value
    assert operation.execution_error == safe_error_message
    assert [asset.status for asset in _assets(context)] == [
        AssetStatus.IDLE.value,
        AssetStatus.IDLE.value,
    ]
    assert [asset.version for asset in _assets(context)] == [1, 1]
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    attempt = db.session.query(OperationExecutionAttempt).one()
    assert attempt.status == "FAILED"
    assert attempt.safe_error_message == safe_error_message
    assert db.session.query(AssetBusinessLock).count() == 2


def test_usage_handlers_expose_exact_safe_failure_messages() -> None:
    module = _handler_module()

    assert (
        module.PersonalUsageHandler.safe_error_message
        == "个人领用执行失败，请联系管理员或稍后重试"
    )
    assert (
        module.PublicUsageHandler.safe_error_message
        == "公共资产投入执行失败，请联系管理员或稍后重试"
    )


def test_personal_usage_submit_expands_child_and_retains_each_location(app) -> None:
    context = seed_usage_return_context()
    context.child_asset.location_id = context.return_location.id
    _grant_usage(context)

    result = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )

    assert result["operation_type"] == OperationType.PERSONAL_USE.value
    assert result["approval_channel"] == ApprovalChannel.FEISHU.value
    assert (
        result["approval_execution_mode"]
        == ApprovalExecutionMode.AUTO_ON_APPROVAL.value
    )
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    assert result["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert result["external_instance_id"] == f"LOCAL-FEISHU-{result['id']}"
    assert result["feature"] == {
        "target_user_id": context.employee.id,
        "target_public_object_id": None,
        "usage_department_id": context.organization.id,
        "target_location_id": None,
    }
    assert [item["asset_id"] for item in result["assets"]] == [
        context.main_asset.id,
        context.child_asset.id,
    ]
    expected_locations = {
        context.main_asset.id: context.location.id,
        context.child_asset.id: context.return_location.id,
    }
    for item in result["assets"]:
        assert item["target_data"] == {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PERSONAL.value,
            "holder_user_id": context.employee.id,
            "public_object_id": None,
            "usage_department_id": context.organization.id,
            "location_id": expected_locations[item["asset_id"]],
        }

    detail = db.session.query(AssetUsageRequest).one()
    assert detail.operation_request_id == result["id"]
    assert detail.target_user_id == context.employee.id
    assert detail.target_public_object_id is None
    assert detail.usage_department_id == context.organization.id
    assert detail.target_location_id is None
    assert db.session.query(OperationRequestAsset).count() == 2
    assert db.session.query(AssetBusinessLock).count() == 2
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(OperationLog).count() == 0


def test_personal_usage_common_location_is_snapshotted_for_every_asset(app) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)

    result = _usage_service().submit_personal(
        _personal_payload(context, location_id=context.return_location.id),
        context.manager.id,
    )

    assert result["feature"]["target_location_id"] == context.return_location.id
    assert {item["target_data"]["location_id"] for item in result["assets"]} == {
        context.return_location.id
    }
    assert db.session.query(AssetUsageRequest).one().target_location_id == (
        context.return_location.id
    )


def test_personal_usage_replays_trimmed_key_before_mutable_validation(app) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    service = _usage_service()

    created = service.submit_personal(
        _personal_payload(context, key="  personal-replay  "),
        context.manager.id,
    )
    context.employee.enabled = False
    context.child_asset.status = AssetStatus.IN_USE.value
    replayed = service.submit_personal(
        {
            "asset_ids": [999_999],
            "target_user_id": -1,
            "idempotency_key": "personal-replay",
        },
        context.manager.id,
    )

    assert replayed == created
    operation = db.session.query(OperationRequest).one()
    assert operation.idempotency_key == "personal-replay"
    assert operation.external_instance_id == f"LOCAL-FEISHU-{operation.id}"
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(AssetUsageRequest).count() == 1
    assert db.session.query(OperationRequestAsset).count() == 2
    assert db.session.query(AssetBusinessLock).count() == 2
    assert db.session.query(ExternalApprovalEvent).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


def test_personal_usage_replay_rejects_missing_feature_detail(app) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
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
        applicant_id=context.manager.id,
        approval_channel=ApprovalChannel.FEISHU.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=[context.main_asset],
        target_data_by_asset_id={context.main_asset.id: target},
        idempotency_key="missing-detail",
    ).operation
    db.session.commit()

    with pytest.raises(BusinessException, match="详情"):
        _usage_service().submit_personal(
            _personal_payload(context, key="missing-detail"),
            context.manager.id,
        )

    assert operation.external_instance_id is None
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(AssetUsageRequest).count() == 0


def test_personal_usage_replay_rejects_detail_targeting_another_valid_user(
    app,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    submitted = _usage_service().submit_personal(
        _personal_payload(context, key="personal-detail-mismatch"),
        context.manager.id,
    )
    other_user = User(
        username="UR-other-valid-target",
        password="x",
        organization_id=context.organization.id,
        enabled=True,
    )
    db.session.add(other_user)
    db.session.flush()
    detail = db.session.query(AssetUsageRequest).one()
    detail.target_user_id = other_user.id
    db.session.commit()

    with pytest.raises(BusinessException, match="不匹配"):
        _usage_service().submit_personal(
            {
                "asset_ids": [999_999],
                "target_user_id": other_user.id,
                "idempotency_key": "personal-detail-mismatch",
            },
            context.manager.id,
        )

    assert db.session.get(OperationRequest, submitted["id"]) is not None
    assert db.session.query(OperationExecutionAttempt).count() == 0


@pytest.mark.parametrize("invalid", ["non_idle", "cross_scope"])
def test_personal_usage_rejects_invalid_expanded_child_without_creating_request(
    app,
    invalid: str,
) -> None:
    context = seed_usage_return_context()
    role = grant_permissions(context.manager, "asset:usage:manage")
    if invalid == "non_idle":
        context.child_asset.status = AssetStatus.IN_USE.value
    else:
        other = Organization(
            code="UR-OTHER-USAGE",
            name="Other usage organization",
            status=RecordStatus.ENABLED.value,
        )
        db.session.add(other)
        db.session.flush()
        role.data_scope = DataScope.DEPARTMENT.value
        context.child_asset.organization_id = other.id

    with pytest.raises(BusinessException):
        _usage_service().submit_personal(
            _personal_payload(context),
            context.manager.id,
        )

    _assert_no_usage_request_data()


def test_personal_usage_requires_manage_permission_before_creating_request(app) -> None:
    context = seed_usage_return_context()

    with pytest.raises(BusinessException, match="权限"):
        _usage_service().submit_personal(
            _personal_payload(context),
            context.manager.id,
        )

    _assert_no_usage_request_data()


def test_personal_approval_executes_batch_once_and_releases_locks(app) -> None:
    context = seed_usage_return_context()
    context.child_asset.location_id = context.return_location.id
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )

    approved = approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id="personal-approved",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=context.manager.id,
    )

    assert approved.approval_status == ApprovalStatus.APPROVED.value
    assert approved.execution_status == ExecutionStatus.SUCCESS.value
    expected_locations = [context.location.id, context.return_location.id]
    for asset, location_id in zip(_assets(context), expected_locations, strict=True):
        assert asset.status == AssetStatus.IN_USE.value
        assert asset.usage_type == UsageType.PERSONAL.value
        assert asset.holder_user_id == context.employee.id
        assert asset.public_object_id is None
        assert asset.usage_department_id == context.organization.id
        assert asset.location_id == location_id
        assert asset.version == 2

    lifecycle_rows = db.session.query(AssetLifecycleRecord).order_by(
        AssetLifecycleRecord.asset_id.asc()
    )
    assert lifecycle_rows.count() == 2
    assert [row.asset_id for row in lifecycle_rows] == [
        context.main_asset.id,
        context.child_asset.id,
    ]
    for row in lifecycle_rows:
        assert row.before_data is not None
        assert row.before_data["status"] == AssetStatus.IDLE.value
        assert row.before_data["version"] == 1
        assert row.after_data is not None
        assert row.after_data["status"] == AssetStatus.IN_USE.value
        assert row.after_data["usage_type"] == UsageType.PERSONAL.value
        assert row.after_data["version"] == 2
    log = db.session.query(OperationLog).one()
    assert log.resource_type == "operation_request"
    assert log.resource_id == str(submitted["id"])
    assert log.before_data == {
        "asset_ids": [context.main_asset.id, context.child_asset.id],
        "asset_count": 2,
    }
    assert log.after_data == {"result": "SUCCESS"}
    assert db.session.query(OperationExecutionAttempt).one().status == "SUCCESS"
    assert db.session.query(AssetBusinessLock).count() == 0

    duplicate = approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id="personal-approved",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=context.manager.id,
    )
    assert duplicate.id == submitted["id"]
    assert db.session.query(ExternalApprovalEvent).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1


def test_personal_rejection_releases_locks_without_execution(app) -> None:
    context = seed_usage_return_context()
    context.child_asset.location_id = context.return_location.id
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )

    rejected = approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id="personal-rejected",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.REJECTED.value,
        actor_id=context.manager.id,
    )

    assert rejected.approval_status == ApprovalStatus.REJECTED.value
    assert rejected.execution_status == ExecutionStatus.NOT_STARTED.value
    for asset, location_id in zip(
        _assets(context),
        [context.location.id, context.return_location.id],
        strict=True,
    ):
        assert asset.status == AssetStatus.IDLE.value
        assert asset.usage_type is None
        assert asset.holder_user_id is None
        assert asset.public_object_id is None
        assert asset.usage_department_id is None
        assert asset.location_id == location_id
        assert asset.version == 1
    assert db.session.query(AssetBusinessLock).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


@pytest.mark.parametrize(
    "invalid_target",
    ["disabled_employee", "moved_department", "disabled_retained_location"],
)
def test_personal_execution_revalidates_current_target_state(
    app,
    invalid_target: str,
) -> None:
    context = seed_usage_return_context()
    if invalid_target == "disabled_retained_location":
        context.child_asset.location_id = context.return_location.id
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )
    if invalid_target == "disabled_employee":
        context.employee.enabled = False
    elif invalid_target == "moved_department":
        other_organization = Organization(
            code="UR-MOVED-TARGET-ORG",
            name="Moved target organization",
            status=RecordStatus.ENABLED.value,
        )
        db.session.add(other_organization)
        db.session.flush()
        context.employee.organization_id = other_organization.id
    else:
        context.return_location.status = RecordStatus.DISABLED.value
    db.session.commit()

    approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id=f"personal-invalid-current-{invalid_target}",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=context.manager.id,
    )

    _assert_failed_without_asset_updates(
        context,
        submitted["id"],
        "个人领用执行失败，请联系管理员或稍后重试",
    )


def test_public_usage_direct_submission_executes_expanded_batch(app) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    _register_usage_handlers()

    result = _usage_service().submit_public(
        _public_payload(context),
        context.manager.id,
    )

    assert result["operation_type"] == OperationType.PUBLIC_USE.value
    assert result["approval_channel"] == ApprovalChannel.DIRECT.value
    assert (
        result["approval_execution_mode"]
        == ApprovalExecutionMode.AUTO_ON_APPROVAL.value
    )
    assert result["approval_status"] == ApprovalStatus.APPROVED.value
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert result["external_instance_id"] is None
    assert result["feature"] == {
        "target_user_id": None,
        "target_public_object_id": context.public_object.id,
        "usage_department_id": None,
        "target_location_id": context.return_location.id,
    }
    assert len(result["assets"]) == 2
    for item in result["assets"]:
        assert item["target_data"] == {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PUBLIC.value,
            "holder_user_id": None,
            "public_object_id": context.public_object.id,
            "usage_department_id": None,
            "location_id": context.return_location.id,
        }
    detail = db.session.query(AssetUsageRequest).one()
    assert detail.target_user_id is None
    assert detail.target_public_object_id == context.public_object.id
    assert detail.usage_department_id is None
    assert detail.target_location_id == context.return_location.id
    for asset in _assets(context):
        assert asset.status == AssetStatus.IN_USE.value
        assert asset.usage_type == UsageType.PUBLIC.value
        assert asset.holder_user_id is None
        assert asset.public_object_id == context.public_object.id
        assert asset.usage_department_id is None
        assert asset.location_id == context.return_location.id
        assert asset.version == 2
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(OperationExecutionAttempt).one().status == "SUCCESS"
    assert db.session.query(AssetBusinessLock).count() == 0


@pytest.mark.parametrize("invalid_target", ["public_object", "location"])
def test_public_execution_revalidates_current_target_state(
    app,
    invalid_target: str,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    _register_usage_handlers()
    operation = _create_pending_public_usage(context)
    if invalid_target == "public_object":
        context.public_object.status = RecordStatus.DISABLED.value
    else:
        context.return_location.status = RecordStatus.DISABLED.value
    db.session.commit()

    approval_provider_service.confirm_direct(operation.id, context.manager.id)

    _assert_failed_without_asset_updates(
        context,
        operation.id,
        "公共资产投入执行失败，请联系管理员或稍后重试",
    )


@pytest.mark.parametrize("disabled", ["public_object", "location"])
def test_public_usage_rejects_disabled_target_before_request(
    app,
    disabled: str,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    if disabled == "public_object":
        context.public_object.status = RecordStatus.DISABLED.value
    else:
        context.return_location.status = RecordStatus.DISABLED.value

    with pytest.raises(BusinessException):
        _usage_service().submit_public(
            _public_payload(context),
            context.manager.id,
        )

    _assert_no_usage_request_data()
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(OperationLog).count() == 0


def test_public_usage_idempotent_replay_executes_and_audits_once(app) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    _register_usage_handlers()
    service = _usage_service()

    created = service.submit_public(
        _public_payload(context, key="  public-replay  "),
        context.manager.id,
    )
    context.public_object.status = RecordStatus.DISABLED.value
    replayed = service.submit_public(
        {
            "asset_ids": [999_999],
            "public_object_id": -1,
            "location_id": -1,
            "idempotency_key": "public-replay",
        },
        context.manager.id,
    )

    assert replayed == created
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(AssetUsageRequest).count() == 1
    assert db.session.query(OperationRequestAsset).count() == 2
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 0


@pytest.mark.parametrize("mismatch", ["public_object", "common_location"])
def test_public_usage_replay_rejects_detail_snapshot_mismatch(
    app,
    mismatch: str,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_public(
        _public_payload(context, key=f"public-detail-{mismatch}"),
        context.manager.id,
    )
    detail = db.session.query(AssetUsageRequest).one()
    if mismatch == "public_object":
        other_object = PublicUsageObject(
            code="UR-OTHER-PUBLIC-TARGET",
            name="UR Other Public Target",
            status=RecordStatus.ENABLED.value,
        )
        db.session.add(other_object)
        db.session.flush()
        detail.target_public_object_id = other_object.id
    else:
        detail.target_location_id = context.location.id
    db.session.commit()

    with pytest.raises(BusinessException, match="不匹配"):
        _usage_service().submit_public(
            {
                "asset_ids": [999_999],
                "public_object_id": -1,
                "location_id": -1,
                "idempotency_key": f"public-detail-{mismatch}",
            },
            context.manager.id,
        )

    assert db.session.get(OperationRequest, submitted["id"]) is not None
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1


@pytest.mark.parametrize("corruption", ["target", "detail", "version"])
def test_personal_handler_validation_failure_preserves_batch_and_locks(
    app,
    corruption: str,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )
    if corruption == "target":
        snapshot = (
            db.session.query(OperationRequestAsset)
            .order_by(OperationRequestAsset.asset_id.asc())
            .first()
        )
        assert snapshot is not None
        snapshot.target_data = {**snapshot.target_data, "unexpected": True}
    elif corruption == "detail":
        detail = db.session.query(AssetUsageRequest).one()
        detail.target_user_id = None
    else:
        context.child_asset.version += 1
    db.session.commit()

    failed = approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id=f"personal-invalid-{corruption}",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=context.manager.id,
    )

    assert failed.approval_status == ApprovalStatus.APPROVED.value
    assert failed.execution_status == ExecutionStatus.FAILED.value
    assert failed.execution_error == "个人领用执行失败，请联系管理员或稍后重试"
    assert [asset.status for asset in _assets(context)] == [
        AssetStatus.IDLE.value,
        AssetStatus.IDLE.value,
    ]
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    attempt = db.session.query(OperationExecutionAttempt).one()
    assert attempt.status == "FAILED"
    assert attempt.safe_error_message == failed.execution_error
    assert db.session.query(AssetBusinessLock).count() == 2


@pytest.mark.parametrize(
    "corruption",
    [
        "asset_status_snapshot",
        "organization_id_snapshot",
        "before_status",
        "before_version",
        "before_location",
        "holder_snapshot",
        "location_snapshot",
    ],
)
def test_usage_handler_rejects_corrupt_snapshot_and_audit_data(
    app,
    corruption: str,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )
    snapshot = (
        db.session.query(OperationRequestAsset)
        .order_by(OperationRequestAsset.asset_id.asc())
        .first()
    )
    assert snapshot is not None
    if corruption == "asset_status_snapshot":
        snapshot.asset_status_snapshot = AssetStatus.IN_USE.value
    elif corruption == "organization_id_snapshot":
        snapshot.organization_id_snapshot = context.organization.id + 10_000
    elif corruption == "before_status":
        snapshot.before_data = {
            **snapshot.before_data,
            "status": AssetStatus.IN_USE.value,
        }
    elif corruption == "before_version":
        snapshot.before_data = {**snapshot.before_data, "version": 99}
    elif corruption == "before_location":
        snapshot.before_data = {
            **snapshot.before_data,
            "location_id": context.return_location.id,
        }
    elif corruption == "holder_snapshot":
        snapshot.holder_snapshot = {"id": context.manager.id, "name": "Corrupt"}
    else:
        snapshot.location_snapshot = {
            "id": context.return_location.id,
            "code": context.return_location.code,
            "name": context.return_location.name,
        }
    db.session.commit()

    approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id=f"personal-corrupt-snapshot-{corruption}",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=context.manager.id,
    )

    _assert_failed_without_asset_updates(
        context,
        submitted["id"],
        "个人领用执行失败，请联系管理员或稍后重试",
    )


def test_usage_handler_rejects_boolean_value_for_integer_target_id(app) -> None:
    context = seed_usage_return_context()
    assert context.manager.id == 1
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_personal(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.manager.id,
        },
        context.manager.id,
    )
    snapshot = (
        db.session.query(OperationRequestAsset)
        .order_by(OperationRequestAsset.asset_id.asc())
        .first()
    )
    assert snapshot is not None
    snapshot.target_data = {**snapshot.target_data, "holder_user_id": True}
    flag_modified(snapshot, "target_data")
    db.session.commit()
    db.session.expire_all()
    persisted_snapshot = (
        db.session.query(OperationRequestAsset)
        .order_by(OperationRequestAsset.asset_id.asc())
        .first()
    )
    assert persisted_snapshot is not None
    assert persisted_snapshot.target_data["holder_user_id"] is True
    assert type(db.session.query(AssetUsageRequest).one().target_user_id) is int

    approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id="personal-boolean-holder-id",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=context.manager.id,
    )

    _assert_failed_without_asset_updates(
        context,
        submitted["id"],
        "个人领用执行失败，请联系管理员或稍后重试",
    )


def test_usage_handler_cas_conflict_rolls_back_whole_batch(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    _grant_usage(context)
    _register_usage_handlers()
    submitted = _usage_service().submit_personal(
        _personal_payload(context),
        context.manager.id,
    )
    original_cas_update = asset_repository.cas_update
    calls = 0

    def conflict_on_second(
        asset_id: int,
        expected_version: int,
        changes: dict[str, object],
    ) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            return False
        return original_cas_update(asset_id, expected_version, changes)

    monkeypatch.setattr(asset_repository, "cas_update", conflict_on_second)

    failed = approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id="personal-cas-conflict",
        external_instance_id=submitted["external_instance_id"],
        status=ApprovalStatus.APPROVED.value,
        actor_id=context.manager.id,
    )

    assert calls == 2
    assert failed.execution_status == ExecutionStatus.FAILED.value
    assert [asset.status for asset in _assets(context)] == [
        AssetStatus.IDLE.value,
        AssetStatus.IDLE.value,
    ]
    assert [asset.version for asset in _assets(context)] == [1, 1]
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    assert db.session.query(OperationExecutionAttempt).one().status == "FAILED"
    assert db.session.query(AssetBusinessLock).count() == 2
