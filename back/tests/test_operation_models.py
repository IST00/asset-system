"""Persistence contracts for the shared operation foundation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import JSON, UniqueConstraint

import app.enums as domain_enums
import app.models as domain_models
import app.repositories as domain_repositories
from app.enums import (
    ApprovalStatus,
    AssetDataCompleteness,
    AssetStatus,
    ExecutionStatus,
    FlowStatus,
)
from app.extensions import db
from app.models import (
    ApprovalFlowAssigneeRule,
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
    ApprovalStep,
    ApprovalTask,
    Asset,
    AssetBusinessLock,
    AssetCategory,
    AssetLocation,
    AssetSource,
    OperationExecutionAttempt,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    Unit,
    User,
)


def _enum_values(name: str) -> set[str]:
    enum_type = getattr(domain_enums, name, None)
    assert enum_type is not None, f"missing enum {name}"
    assert issubclass(enum_type, Enum)
    return {item.value for item in enum_type}


def _foreign_key(column_name: str):
    foreign_keys = list(Asset.__table__.columns[column_name].foreign_keys)
    assert len(foreign_keys) == 1
    return foreign_keys[0]


def _model(name: str):
    model = getattr(domain_models, name, None)
    assert model is not None, f"missing model {name}"
    return model


def _unique_column_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _repository(name: str):
    repository = getattr(domain_repositories, name, None)
    assert repository is not None, f"missing repository {name}"
    return repository


def _seed_asset_pair() -> tuple[User, OperationRequest, Asset, Asset]:
    organization = Organization(code="REPO-ORG", name="仓储测试组织")
    unit = Unit(code="REPO-UNIT", name="仓储测试单位")
    source = AssetSource(code="REPO-SOURCE", name="仓储测试来源")
    location = AssetLocation(
        code="REPO-LOCATION", name="仓储测试地点", is_selectable=True
    )
    applicant = User(username="repo-applicant", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, applicant])
    db.session.flush()
    category = AssetCategory(
        code="REPO-CATEGORY",
        name="仓储测试分类",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    assets = [
        Asset(
            asset_code=f"REPO-ASSET-{index}",
            asset_name=f"仓储测试资产{index}",
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=unit.id,
            original_amount=Decimal("1.00"),
            purchase_date=date(2026, 7, 17),
            service_life_months=36,
            expected_expiry_date=date(2029, 1, 1),
            manager_id=applicant.id,
            source_id=source.id,
            location_id=location.id,
            custom_attributes={},
            data_completeness=AssetDataCompleteness.COMPLETE.value,
        )
        for index in (1, 2)
    ]
    operation = OperationRequest(
        request_no="REPO-REQUEST",
        operation_type="TRANSFER",
        applicant_id=applicant.id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add_all([*assets, operation])
    db.session.flush()
    return applicant, operation, assets[0], assets[1]


def test_operation_foundation_enums_expose_stable_persisted_values() -> None:
    assert _enum_values("ApprovalChannel") == {"INTERNAL", "FEISHU", "DIRECT"}
    assert _enum_values("SignMode") == {"OR_SIGN", "AND_SIGN"}
    assert _enum_values("AssigneeType") == {"USER", "ROLE"}
    assert _enum_values("FlowStatus") == {"DRAFT", "PUBLISHED", "DISABLED"}
    assert _enum_values("RuntimeTaskStatus") == {
        "WAITING",
        "PENDING",
        "APPROVED",
        "REJECTED",
        "WITHDRAWN",
    }
    assert _enum_values("ExecutionAttemptStatus") == {
        "PROCESSING",
        "SUCCESS",
        "FAILED",
    }
    assert _enum_values("UsageType") == {"PERSONAL", "PUBLIC"}
    assert _enum_values("OperationType") == {
        "STOCK_IN",
        "PERSONAL_USE",
        "PUBLIC_USE",
        "PERSONAL_RETURN",
        "PUBLIC_RETURN",
        "TRANSFER",
        "REPAIR_START",
        "REPAIR_COMPLETE",
    }
    assert _enum_values("ApprovalExecutionMode") == {
        "AUTO_ON_APPROVAL",
        "MANUAL_CONFIRM",
    }
    assert _enum_values("ExecutionTriggerType") == {
        "APPROVAL",
        "CONFIRMATION",
        "RETRY",
    }


def test_asset_exposes_nullable_usage_and_single_level_parent_fields() -> None:
    columns = Asset.__table__.columns

    for column_name in (
        "usage_type",
        "holder_user_id",
        "public_object_id",
        "usage_department_id",
        "parent_asset_id",
    ):
        assert column_name in columns
        assert columns[column_name].nullable is True

    assert columns["version"].nullable is False
    assert _foreign_key("holder_user_id").target_fullname == "users.id"
    assert _foreign_key("holder_user_id").ondelete == "SET NULL"
    assert _foreign_key("public_object_id").target_fullname == "public_usage_objects.id"
    assert _foreign_key("public_object_id").ondelete == "RESTRICT"
    assert _foreign_key("usage_department_id").target_fullname == "organizations.id"
    assert _foreign_key("usage_department_id").ondelete == "SET NULL"
    assert _foreign_key("parent_asset_id").target_fullname == "assets.id"
    assert _foreign_key("parent_asset_id").ondelete == "RESTRICT"


def test_public_usage_object_is_distinct_from_login_users(app) -> None:
    model = getattr(domain_models, "PublicUsageObject", None)
    assert model is not None, "missing PublicUsageObject model"

    table = model.__table__
    assert table.name == "public_usage_objects"
    assert set(table.columns.keys()) == {
        "id",
        "code",
        "name",
        "status",
        "created_at",
        "updated_at",
    }
    assert table.columns.code.nullable is False
    assert table.columns.code.unique is True
    assert table.columns.name.nullable is False
    assert table.columns.name.unique is True
    assert table.columns.status.nullable is False
    assert not {"username", "password", "organization_id"} & set(table.columns.keys())


def test_operation_request_has_lifecycle_and_idempotency_contract() -> None:
    operation_request = _model("OperationRequest")
    columns = operation_request.__table__.columns

    assert {
        "parent_request_id",
        "approval_channel",
        "approval_flow_version_id",
        "external_instance_id",
        "idempotency_key",
        "submitted_at",
        "approved_at",
        "executed_at",
        "terminated_at",
        "terminated_by",
        "termination_reason",
    } <= set(columns.keys())
    assert columns["flow_version"].nullable is False
    assert columns["approval_channel"].nullable is False
    assert columns["approval_flow_version_id"].nullable is True
    assert columns["idempotency_key"].nullable is True
    assert columns["approval_execution_mode"].nullable is False
    assert columns["approval_execution_mode"].default.arg == "AUTO_ON_APPROVAL"
    assert (
        "applicant_id",
        "operation_type",
        "idempotency_key",
    ) in _unique_column_sets(operation_request)


def test_operation_kernel_models_define_database_uniqueness_guards() -> None:
    assert (
        "operation_request_id",
        "asset_id",
    ) in _unique_column_sets(_model("OperationRequestAsset"))
    assert ("asset_id",) in _unique_column_sets(_model("AssetBusinessLock"))
    assert (
        "operation_request_id",
        "attempt_no",
    ) in _unique_column_sets(_model("OperationExecutionAttempt"))
    assert (
        "provider",
        "external_event_id",
    ) in _unique_column_sets(_model("ExternalApprovalEvent"))
    assert (
        "operation_request_id",
        "actor_id",
        "action",
        "idempotency_key",
    ) in _unique_column_sets(_model("OperationActionIdempotency"))


def test_operation_request_asset_keeps_explicit_and_json_snapshots() -> None:
    snapshot = _model("OperationRequestAsset")
    columns = snapshot.__table__.columns

    assert {
        "asset_code_snapshot",
        "asset_name_snapshot",
        "asset_status_snapshot",
        "asset_version_snapshot",
        "organization_id_snapshot",
        "holder_snapshot",
        "location_snapshot",
        "before_data",
        "target_data",
    } <= set(columns.keys())
    for column_name in (
        "holder_snapshot",
        "location_snapshot",
        "before_data",
        "target_data",
    ):
        assert isinstance(columns[column_name].type, JSON)


def test_operation_kernel_foreign_keys_reference_existing_aggregates() -> None:
    expected_targets = {
        "OperationRequestAsset": {
            "operation_request_id": "operation_requests.id",
            "asset_id": "assets.id",
        },
        "AssetBusinessLock": {
            "asset_id": "assets.id",
            "operation_request_id": "operation_requests.id",
            "applicant_id": "users.id",
        },
        "OperationExecutionAttempt": {
            "operation_request_id": "operation_requests.id",
            "triggered_by": "users.id",
        },
        "ExternalApprovalEvent": {
            "operation_request_id": "operation_requests.id",
        },
        "OperationActionIdempotency": {
            "operation_request_id": "operation_requests.id",
            "actor_id": "users.id",
        },
    }

    for model_name, column_targets in expected_targets.items():
        columns = _model(model_name).__table__.columns
        for column_name, target in column_targets.items():
            foreign_keys = list(columns[column_name].foreign_keys)
            assert len(foreign_keys) == 1
            assert foreign_keys[0].target_fullname == target


def test_approval_flow_models_define_versioned_unique_graph() -> None:
    assert ("operation_type",) in _unique_column_sets(_model("ApprovalFlowDefinition"))
    assert (
        "flow_definition_id",
        "version_no",
    ) in _unique_column_sets(_model("ApprovalFlowVersion"))
    assert (
        "flow_version_id",
        "level_no",
    ) in _unique_column_sets(_model("ApprovalFlowLayer"))
    assert (
        "layer_id",
        "assignee_type",
        "assignee_id",
    ) in _unique_column_sets(_model("ApprovalFlowAssigneeRule"))


def test_approval_flow_models_use_explicit_fields_without_scripts() -> None:
    definition_columns = _model("ApprovalFlowDefinition").__table__.columns
    version_columns = _model("ApprovalFlowVersion").__table__.columns
    layer_columns = _model("ApprovalFlowLayer").__table__.columns
    rule_columns = _model("ApprovalFlowAssigneeRule").__table__.columns

    assert {"operation_type", "name", "status", "version"} <= set(
        definition_columns.keys()
    )
    assert {
        "flow_definition_id",
        "version_no",
        "status",
        "published_at",
        "published_by",
    } <= set(version_columns.keys())
    assert {
        "flow_version_id",
        "level_no",
        "sign_mode",
        "allow_self_approval",
    } <= set(layer_columns.keys())
    assert {"layer_id", "assignee_type", "assignee_id"} <= set(rule_columns.keys())
    for columns in (
        definition_columns,
        version_columns,
        layer_columns,
        rule_columns,
    ):
        assert not {"expression", "script"} & set(columns.keys())


def test_approval_runtime_supports_layer_and_task_level_decisions() -> None:
    approval_step = _model("ApprovalStep")
    approval_task = _model("ApprovalTask")
    approval_record = _model("ApprovalRecord")

    assert {"flow_layer_id", "sign_mode", "status", "version"} <= set(
        approval_step.__table__.columns.keys()
    )
    assert {"approver_id", "status", "version"} <= set(
        approval_task.__table__.columns.keys()
    )
    assert ("approval_task_id",) in _unique_column_sets(approval_record)
    assert ("approval_step_id",) not in _unique_column_sets(approval_record)


def test_operation_request_references_immutable_flow_version() -> None:
    column = _model("OperationRequest").__table__.columns["approval_flow_version_id"]
    foreign_keys = list(column.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "approval_flow_versions.id"
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_operation_repositories_order_rows_release_locks_and_number_attempts(
    app,
) -> None:
    applicant, operation, first_asset, second_asset = _seed_asset_pair()
    request_asset_repository = _repository("operation_request_asset_repository")
    lock_repository = _repository("asset_business_lock_repository")
    attempt_repository = _repository("execution_attempt_repository")

    snapshots = [
        OperationRequestAsset(
            operation_request_id=operation.id,
            asset_id=asset.id,
            asset_code_snapshot=asset.asset_code,
            asset_name_snapshot=asset.asset_name,
            asset_status_snapshot=asset.status,
            asset_version_snapshot=asset.version,
            organization_id_snapshot=asset.organization_id,
        )
        for asset in (second_asset, first_asset)
    ]
    db.session.add_all(snapshots)
    db.session.flush()
    assert [
        item.asset_id for item in request_asset_repository.find_by_request(operation.id)
    ] == [first_asset.id, second_asset.id]

    locks = [
        AssetBusinessLock(
            asset_id=asset.id,
            operation_request_id=operation.id,
            operation_type=operation.operation_type,
            applicant_id=applicant.id,
        )
        for asset in (second_asset, first_asset)
    ]
    lock_repository.acquire_rows(locks)
    persisted_locks = db.session.query(AssetBusinessLock).order_by(AssetBusinessLock.id)
    assert [item.asset_id for item in persisted_locks] == [
        first_asset.id,
        second_asset.id,
    ]

    db.session.add_all(
        [
            OperationExecutionAttempt(
                operation_request_id=operation.id,
                attempt_no=attempt_no,
                trigger_type="RETRY",
                triggered_by=applicant.id,
                status="FAILED",
            )
            for attempt_no in (1, 2)
        ]
    )
    db.session.flush()
    assert attempt_repository.next_attempt_no(operation.id) == 3

    lock_repository.release_for_request(operation.id)
    db.session.flush()
    assert db.session.query(AssetBusinessLock).count() == 0


def test_approval_flow_repository_loads_latest_published_ordered_graph(app) -> None:
    actor = User(username="flow-repo-actor", password="x", enabled=True)
    db.session.add(actor)
    db.session.flush()
    definition = ApprovalFlowDefinition(
        operation_type="TRANSFER",
        name="调拨审批",
        status=FlowStatus.PUBLISHED.value,
    )
    db.session.add(definition)
    db.session.flush()
    versions = [
        ApprovalFlowVersion(
            flow_definition_id=definition.id,
            version_no=version_no,
            status=FlowStatus.PUBLISHED.value,
            published_by=actor.id,
        )
        for version_no in (1, 2)
    ]
    db.session.add_all(versions)
    db.session.flush()
    layers = [
        ApprovalFlowLayer(
            flow_version_id=versions[1].id,
            level_no=level_no,
            sign_mode="OR_SIGN",
        )
        for level_no in (2, 1)
    ]
    db.session.add_all(layers)
    db.session.flush()
    db.session.add_all(
        [
            ApprovalFlowAssigneeRule(
                layer_id=layer.id,
                assignee_type="USER",
                assignee_id=actor.id,
            )
            for layer in layers
        ]
    )
    db.session.flush()

    repository = _repository("approval_flow_repository")
    assert repository.find_published("TRANSFER").id == versions[1].id
    assert repository.next_version_no(definition.id) == 3
    loaded = repository.load_version_graph(versions[1].id)
    assert loaded is not None
    assert [layer.level_no for layer in loaded.layers] == [1, 2]
    assert all(len(layer.assignee_rules) == 1 for layer in loaded.layers)


def test_runtime_repositories_find_current_rows_for_update(app) -> None:
    applicant = User(username="runtime-applicant", password="x", enabled=True)
    approver = User(username="runtime-approver", password="x", enabled=True)
    db.session.add_all([applicant, approver])
    db.session.flush()
    operation = OperationRequest(
        request_no="RUNTIME-REQUEST",
        operation_type="TRANSFER",
        applicant_id=applicant.id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add(operation)
    db.session.flush()
    later = ApprovalStep(
        operation_request_id=operation.id,
        level_no=2,
        status="WAITING",
    )
    current = ApprovalStep(
        operation_request_id=operation.id,
        level_no=1,
        status="PENDING",
    )
    db.session.add_all([later, current])
    db.session.flush()
    task = ApprovalTask(
        approval_step_id=current.id,
        approver_id=approver.id,
        status="PENDING",
    )
    db.session.add(task)
    db.session.flush()

    step_repository = _repository("approval_step_repository")
    task_repository = _repository("approval_task_repository")
    assert step_repository.find_current_for_update(operation.id).id == current.id
    assert task_repository.find_for_update(current.id, approver.id).id == task.id
