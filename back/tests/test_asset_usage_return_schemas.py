"""Schemas and shared validation for asset usage and return workflows."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date, timedelta
from types import ModuleType
from typing import Any

import pytest
from marshmallow import Schema, ValidationError

import asset_usage_return_fixtures as usage_return_fixtures
import app.services.asset_usage_return_support as usage_return_support
from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetDataCompleteness,
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
    OperationRequest,
    OperationRequestAsset,
    Organization,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from app.models.mixins import utc_now
from app.operations.registry import OperationHandlerRegistry
from app.schemas.asset_usage_return import (
    MockFeishuActionSchema,
    PersonalBorrowCreateSchema,
    PersonalReturnCreateSchema,
    PersonalUsageCreateSchema,
    PublicBorrowCreateSchema,
    PublicReturnCreateSchema,
    PublicUsageCreateSchema,
    ReturnConfirmSchema,
    ReturnInspectionSchema,
    UsageReturnPageQuerySchema,
)
from app.services.asset_usage_return_support import (
    expand_assets,
    operation_assets,
    require_assets_in_scope,
    require_idle_assets,
    require_location,
    require_personal_assets,
    require_personal_target,
    require_public_assets,
    require_public_target,
    serialize_operation,
)
from asset_usage_return_fixtures import (
    grant_permissions,
    seed_usage_return_context,
)


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (PersonalUsageCreateSchema(), {"target_user_id": 1}),
        (PersonalUsageCreateSchema(), {"asset_ids": [], "target_user_id": 1}),
        (
            PersonalUsageCreateSchema(),
            {"asset_ids": [1, 1], "target_user_id": 1},
        ),
        (PersonalUsageCreateSchema(), {"asset_ids": [1]}),
        (PublicUsageCreateSchema(), {"asset_ids": [1], "location_id": 1}),
    ],
)
def test_usage_schemas_reject_missing_empty_duplicate_assets_or_targets(
    schema: Schema, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        schema.load(payload)


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            PersonalUsageCreateSchema(),
            {"asset_ids": ["1"], "target_user_id": 1},
        ),
        (
            PersonalUsageCreateSchema(),
            {"asset_ids": [True], "target_user_id": 1},
        ),
        (
            PersonalUsageCreateSchema(),
            {"asset_ids": [1], "target_user_id": "1"},
        ),
        (
            PersonalUsageCreateSchema(),
            {"asset_ids": [1], "target_user_id": 1, "location_id": False},
        ),
        (
            PublicUsageCreateSchema(),
            {"asset_ids": [1], "public_object_id": "1", "location_id": 1},
        ),
        (
            PublicUsageCreateSchema(),
            {"asset_ids": [1], "public_object_id": 1, "location_id": True},
        ),
        (
            ReturnConfirmSchema(),
            {
                "return_location_id": "1",
                "items": [{"asset_id": 1, "condition": "NORMAL"}],
            },
        ),
        (
            ReturnConfirmSchema(),
            {
                "return_location_id": 1,
                "items": [{"asset_id": False, "condition": "NORMAL"}],
            },
        ),
    ],
)
def test_strict_integer_fields_reject_strings_and_booleans(
    schema: Schema, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        schema.load(payload)


def test_borrow_schemas_require_concrete_assets_and_return_time() -> None:
    with pytest.raises(ValidationError):
        PersonalBorrowCreateSchema().load(
            {"target_user_id": 1, "expected_return_at": "2026-09-10T09:00:00Z"}
        )
    with pytest.raises(ValidationError):
        PublicBorrowCreateSchema().load(
            {
                "asset_ids": [1],
                "public_object_id": 2,
                "location_id": 3,
            }
        )


def test_borrow_schemas_parse_utc_return_time() -> None:
    personal = PersonalBorrowCreateSchema().load(
        {
            "asset_ids": [1],
            "target_user_id": 2,
            "expected_return_at": "2026-09-10T09:00:00+08:00",
        }
    )
    public = PublicBorrowCreateSchema().load(
        {
            "asset_ids": [1],
            "public_object_id": 2,
            "location_id": 3,
            "expected_return_at": "2026-09-10T01:00:00Z",
        }
    )

    assert personal["expected_return_at"].isoformat() == "2026-09-10T01:00:00+00:00"
    assert public["expected_return_at"].isoformat() == "2026-09-10T01:00:00+00:00"


def test_asset_ids_reject_more_than_one_hundred_items() -> None:
    with pytest.raises(ValidationError) as error:
        PersonalReturnCreateSchema().load({"asset_ids": list(range(101))})

    assert "asset_ids" in error.value.messages


@pytest.mark.parametrize("idempotency_key", ["", "x" * 192])
def test_idempotency_key_rejects_invalid_lengths(idempotency_key: str) -> None:
    with pytest.raises(ValidationError) as error:
        PersonalReturnCreateSchema().load(
            {"asset_ids": [1], "idempotency_key": idempotency_key}
        )

    assert "idempotency_key" in error.value.messages


def test_personal_usage_accepts_nullable_location() -> None:
    loaded = PersonalUsageCreateSchema().load(
        {"asset_ids": [1], "target_user_id": 2, "location_id": None}
    )

    assert loaded["location_id"] is None


def test_public_usage_requires_location() -> None:
    with pytest.raises(ValidationError) as error:
        PublicUsageCreateSchema().load({"asset_ids": [1], "public_object_id": 2})

    assert "location_id" in error.value.messages


@pytest.mark.parametrize(
    "schema",
    [
        PersonalUsageCreateSchema(),
        PublicUsageCreateSchema(),
        PersonalReturnCreateSchema(),
        PublicReturnCreateSchema(),
    ],
)
def test_all_create_schemas_reject_duplicate_asset_ids(schema: Schema) -> None:
    payload: dict[str, Any] = {"asset_ids": [7, 7]}
    if isinstance(schema, PersonalUsageCreateSchema):
        payload["target_user_id"] = 1
    elif isinstance(schema, PublicUsageCreateSchema):
        payload.update(public_object_id=1, location_id=1)
    elif isinstance(schema, PublicReturnCreateSchema):
        payload.update(
            **_return_destination_fields(),
            items=[{"asset_id": 7, "condition": "NORMAL"}],
        )

    with pytest.raises(ValidationError, match="重复"):
        schema.load(payload)


def test_personal_return_rejects_holder_override() -> None:
    with pytest.raises(ValidationError) as error:
        PersonalReturnCreateSchema().load({"asset_ids": [1], "target_user_id": 99})

    assert "target_user_id" in error.value.messages


@pytest.mark.parametrize("schema", [PublicReturnCreateSchema(), ReturnConfirmSchema()])
def test_return_schemas_reject_duplicate_inspection_asset_ids(schema: Schema) -> None:
    payload = {
        **_return_destination_fields(),
        "items": [
            {"asset_id": 7, "condition": "NORMAL"},
            {
                "asset_id": 7,
                "condition": "DAMAGED",
                "condition_description": "划痕",
            },
        ],
    }
    if isinstance(schema, PublicReturnCreateSchema):
        payload["asset_ids"] = [7]

    with pytest.raises(ValidationError, match="重复"):
        schema.load(payload)


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"asset_id": index, "condition": "NORMAL"} for index in range(101)],
    ],
)
@pytest.mark.parametrize("schema", [PublicReturnCreateSchema(), ReturnConfirmSchema()])
def test_return_items_require_between_one_and_one_hundred_entries(
    schema: Schema,
    items: list[dict[str, Any]],
) -> None:
    payload: dict[str, Any] = {
        **_return_destination_fields(),
        "items": items,
    }
    if isinstance(schema, PublicReturnCreateSchema):
        payload["asset_ids"] = [1]

    with pytest.raises(ValidationError) as error:
        schema.load(payload)

    assert "items" in error.value.messages


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            PublicReturnCreateSchema(),
            {
                "return_company_id": 1,
                "return_usage_company_id": 1,
                "return_region_id": 1,
                "asset_ids": [1],
                "items": [{"asset_id": 1, "condition": "NORMAL"}],
            },
        ),
        (
            ReturnConfirmSchema(),
            {
                "return_company_id": 1,
                "return_usage_company_id": 1,
                "return_region_id": 1,
                "items": [{"asset_id": 1, "condition": "NORMAL"}],
            },
        ),
    ],
)
def test_return_schemas_require_return_location(
    schema: Schema, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as error:
        schema.load(payload)

    assert "return_location_id" in error.value.messages


@pytest.mark.parametrize("idempotency_key", ["x", "x" * 191])
def test_return_confirm_accepts_idempotency_key_boundaries(
    idempotency_key: str,
) -> None:
    loaded = ReturnConfirmSchema().load(
        {
            **_return_destination_fields(),
            "items": [{"asset_id": 1, "condition": "NORMAL"}],
            "idempotency_key": idempotency_key,
        }
    )

    assert loaded["idempotency_key"] == idempotency_key


@pytest.mark.parametrize("idempotency_key", ["", "x" * 192])
def test_return_confirm_rejects_invalid_idempotency_key_lengths(
    idempotency_key: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        ReturnConfirmSchema().load(
            {
                **_return_destination_fields(),
                "items": [{"asset_id": 1, "condition": "NORMAL"}],
                "idempotency_key": idempotency_key,
            }
        )

    assert "idempotency_key" in error.value.messages


def _return_destination_fields(location_id: int = 1) -> dict[str, int]:
    return {
        "return_company_id": location_id,
        "return_usage_company_id": location_id,
        "return_region_id": location_id,
        "return_location_id": location_id,
    }


def _payload_with_idempotency_key(schema: Schema, key: str) -> dict[str, Any]:
    if isinstance(schema, PersonalReturnCreateSchema):
        return {"asset_ids": [1], "idempotency_key": key}
    return {
        **_return_destination_fields(),
        "items": [{"asset_id": 1, "condition": "NORMAL"}],
        "idempotency_key": key,
    }


@pytest.mark.parametrize(
    "schema", [PersonalReturnCreateSchema(), ReturnConfirmSchema()]
)
@pytest.mark.parametrize(
    ("raw_key", "normalized_key"),
    [(" x ", "x"), (f" {'x' * 191} ", "x" * 191)],
)
def test_idempotency_keys_are_stripped_before_valid_length_checks(
    schema: Schema,
    raw_key: str,
    normalized_key: str,
) -> None:
    loaded = schema.load(_payload_with_idempotency_key(schema, raw_key))

    assert loaded["idempotency_key"] == normalized_key


@pytest.mark.parametrize(
    "schema", [PersonalReturnCreateSchema(), ReturnConfirmSchema()]
)
@pytest.mark.parametrize("raw_key", ["   ", f" {'x' * 192} "])
def test_normalized_idempotency_keys_still_enforce_length_boundaries(
    schema: Schema,
    raw_key: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        schema.load(_payload_with_idempotency_key(schema, raw_key))

    assert "idempotency_key" in error.value.messages


def test_create_schema_accepts_one_hundred_assets_and_191_char_key() -> None:
    key = "x" * 191

    loaded = PersonalReturnCreateSchema().load(
        {"asset_ids": list(range(1, 101)), "idempotency_key": key}
    )

    assert len(loaded["asset_ids"]) == 100
    assert loaded["idempotency_key"] == key


def test_return_confirm_accepts_one_hundred_inspection_items() -> None:
    loaded = ReturnConfirmSchema().load(
        {
            **_return_destination_fields(),
            "items": [
                {"asset_id": asset_id, "condition": "NORMAL"}
                for asset_id in range(1, 101)
            ],
        }
    )

    assert len(loaded["items"]) == 100


def test_inspection_rejects_invalid_condition() -> None:
    with pytest.raises(ValidationError) as error:
        ReturnInspectionSchema().load({"asset_id": 1, "condition": "LOST"})

    assert "condition" in error.value.messages


def test_inspection_rejects_description_over_two_thousand_characters() -> None:
    with pytest.raises(ValidationError) as error:
        ReturnInspectionSchema().load(
            {
                "asset_id": 1,
                "condition": "DAMAGED",
                "condition_description": "x" * 2001,
            }
        )

    assert "condition_description" in error.value.messages


@pytest.mark.parametrize("description", [None, "", "   "])
def test_damaged_inspection_requires_nonblank_description(
    description: str | None,
) -> None:
    payload: dict[str, Any] = {"asset_id": 1, "condition": "DAMAGED"}
    if description is not None:
        payload["condition_description"] = description

    with pytest.raises(ValidationError) as error:
        ReturnInspectionSchema().load(payload)

    assert "condition_description" in error.value.messages


def test_inspection_strips_damage_description_and_clears_normal_description() -> None:
    damaged = ReturnInspectionSchema().load(
        {
            "asset_id": 1,
            "condition": "DAMAGED",
            "condition_description": "  外壳划痕  ",
        }
    )
    normal = ReturnInspectionSchema().load(
        {
            "asset_id": 2,
            "condition": "NORMAL",
            "condition_description": "  不应保留  ",
        }
    )

    assert damaged["condition_description"] == "外壳划痕"
    assert normal["condition_description"] is None


def test_mock_feishu_reject_requires_event_and_reason() -> None:
    schema = MockFeishuActionSchema()

    with pytest.raises(ValidationError) as missing_event:
        schema.load({"action": "REJECT", "reason": "拒绝"})
    assert "external_event_id" in missing_event.value.messages

    with pytest.raises(ValidationError) as blank_reason:
        schema.load(
            {
                "action": "REJECT",
                "external_event_id": "event-1",
                "reason": "   ",
            }
        )
    assert "reason" in blank_reason.value.messages


def test_mock_feishu_action_strips_strings_and_normalizes_blank_reason() -> None:
    rejected = MockFeishuActionSchema().load(
        {
            "action": "REJECT",
            "external_event_id": "  event-1  ",
            "reason": "  不同意  ",
        }
    )
    approved = MockFeishuActionSchema().load(
        {
            "action": "APPROVE",
            "external_event_id": "  event-2  ",
            "reason": "   ",
        }
    )

    assert rejected["external_event_id"] == "event-1"
    assert rejected["reason"] == "不同意"
    assert approved["reason"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "CANCEL", "external_event_id": "event-1"},
        {"action": "APPROVE", "external_event_id": "   "},
        {"action": "APPROVE", "external_event_id": "x" * 192},
        {
            "action": "APPROVE",
            "external_event_id": "event-1",
            "reason": "x" * 2001,
        },
    ],
)
def test_mock_feishu_rejects_invalid_action_event_or_reason(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        MockFeishuActionSchema().load(payload)


def test_usage_return_page_query_defaults_and_rejects_oversize_page() -> None:
    assert UsageReturnPageQuerySchema().load({}) == {"page": 0, "size": 50}

    with pytest.raises(ValidationError):
        UsageReturnPageQuerySchema().load({"size": 101})


def test_usage_return_page_query_accepts_maximum_size() -> None:
    assert UsageReturnPageQuerySchema().load({"size": 100})["size"] == 100


@pytest.mark.parametrize("payload", [{"page": -1}, {"size": 0}])
def test_usage_return_page_query_rejects_invalid_lower_bounds(
    payload: dict[str, int],
) -> None:
    with pytest.raises(ValidationError):
        UsageReturnPageQuerySchema().load(payload)


@pytest.mark.parametrize(
    ("schema", "payload", "field_name"),
    [
        (
            PersonalReturnCreateSchema(),
            {"asset_ids": [1], "unexpected": True},
            "unexpected",
        ),
        (
            ReturnConfirmSchema(),
            {
                **_return_destination_fields(),
                "items": [{"asset_id": 1, "condition": "NORMAL", "unexpected": True}],
            },
            "items",
        ),
    ],
)
def test_unknown_root_and_nested_fields_are_rejected(
    schema: Schema,
    payload: dict[str, Any],
    field_name: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        schema.load(payload)

    assert field_name in error.value.messages


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (ReturnInspectionSchema(), 7),
        (ReturnInspectionSchema(), ["not-an-object"]),
        (
            ReturnInspectionSchema(),
            [("asset_id", 1), ("condition", "NORMAL")],
        ),
        (MockFeishuActionSchema(), 7),
        (MockFeishuActionSchema(), ["not-an-object"]),
        (
            MockFeishuActionSchema(),
            [("action", "APPROVE"), ("external_event_id", "event-1")],
        ),
    ],
    ids=[
        "inspection-scalar",
        "inspection-list",
        "inspection-pairs",
        "mock-scalar",
        "mock-list",
        "mock-pairs",
    ],
)
def test_schema_preload_hooks_reject_non_mapping_roots_without_raw_errors(
    schema: Schema,
    payload: object,
) -> None:
    with pytest.raises(ValidationError):
        schema.load(payload)


@pytest.mark.parametrize(
    "item",
    [
        7,
        ["not-an-object"],
        [("asset_id", 1), ("condition", "NORMAL")],
    ],
    ids=["scalar", "list", "pairs"],
)
def test_nested_inspection_rejects_non_mapping_values_without_raw_errors(
    item: object,
) -> None:
    with pytest.raises(ValidationError):
        ReturnConfirmSchema().load({**_return_destination_fields(), "items": [item]})


def test_expand_assets_adds_direct_child_and_rejects_child_only(app) -> None:
    context = seed_usage_return_context()

    expanded = expand_assets([context.main_asset.id])

    assert [asset.id for asset in expanded] == [
        context.main_asset.id,
        context.child_asset.id,
    ]
    with pytest.raises(BusinessException, match="解除.*关系"):
        expand_assets([context.child_asset.id])


def _independent_asset(context: Any, suffix: str) -> Asset:
    return Asset(
        asset_code=f"UR-ASSET-{suffix}",
        asset_name=f"UR Independent Asset {suffix}",
        status=AssetStatus.IDLE.value,
        organization_id=context.organization.id,
        category_id=context.main_asset.category_id,
        unit_id=context.main_asset.unit_id,
        original_amount=context.main_asset.original_amount,
        purchase_date=context.main_asset.purchase_date,
        service_life_months=36,
        expected_expiry_date=date(2029, 1, 1),
        manager_id=context.manager.id,
        source_id=context.main_asset.source_id,
        location_id=context.location.id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )


def test_expand_assets_returns_globally_stable_order_for_shuffled_roots(app) -> None:
    context = seed_usage_return_context()
    first = _independent_asset(context, "INDEPENDENT-A")
    second = _independent_asset(context, "INDEPENDENT-B")
    db.session.add_all([first, second])
    db.session.flush()

    expanded = expand_assets([second.id, context.main_asset.id, first.id])

    assert [asset.id for asset in expanded] == sorted(
        [
            context.main_asset.id,
            context.child_asset.id,
            first.id,
            second.id,
        ]
    )


def test_expand_assets_rejects_empty_request(app) -> None:
    with pytest.raises(BusinessException, match="至少"):
        expand_assets([])


def test_scope_check_includes_cross_organization_child(app) -> None:
    context = seed_usage_return_context()
    department_role = Role(
        code="UR-DEPARTMENT-SCOPE",
        name="UR Department Scope",
        data_scope=DataScope.DEPARTMENT.value,
    )
    other_organization = Organization(
        code="UR-OTHER-ORG",
        name="UR Other Organization",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add_all([department_role, other_organization])
    db.session.flush()
    db.session.add(UserRole(user_id=context.employee.id, role_id=department_role.id))
    context.child_asset.organization_id = other_organization.id
    db.session.flush()

    expanded = expand_assets([context.main_asset.id])

    with pytest.raises(BusinessException, match="组织"):
        require_assets_in_scope(context.employee.id, expanded)


@pytest.mark.parametrize("allow_all", [False, True])
def test_scope_check_resolves_accessible_organizations_once_for_allowed_batch(
    app,
    monkeypatch,
    allow_all: bool,
) -> None:
    context = seed_usage_return_context()
    calls = 0

    def accessible_organization_ids(_actor_id: int) -> set[int] | None:
        nonlocal calls
        calls += 1
        return None if allow_all else {context.organization.id}

    monkeypatch.setattr(
        usage_return_support.permission_service,
        "accessible_organization_ids",
        accessible_organization_ids,
    )

    assert (
        require_assets_in_scope(
            context.employee.id,
            [context.main_asset, context.child_asset],
        )
        is None
    )
    assert calls == 1


def test_scope_check_resolves_once_and_rejects_out_of_scope_batch(
    app,
    monkeypatch,
) -> None:
    context = seed_usage_return_context()
    calls = 0

    def accessible_organization_ids(_actor_id: int) -> set[int]:
        nonlocal calls
        calls += 1
        return set()

    monkeypatch.setattr(
        usage_return_support.permission_service,
        "accessible_organization_ids",
        accessible_organization_ids,
    )

    with pytest.raises(BusinessException) as error:
        require_assets_in_scope(
            context.employee.id,
            [context.main_asset, context.child_asset],
        )

    assert error.value.code == ResultCode.FORBIDDEN.code
    assert error.value.message == "无该组织的数据权限"
    assert calls == 1


def test_mixed_asset_states_and_usage_types_are_rejected(app) -> None:
    context = seed_usage_return_context()
    context.child_asset.status = AssetStatus.IN_USE.value

    with pytest.raises(BusinessException):
        require_idle_assets([context.main_asset, context.child_asset])

    context.main_asset.status = AssetStatus.IN_USE.value
    context.main_asset.usage_type = UsageType.PERSONAL.value
    context.main_asset.holder_user_id = context.employee.id
    context.child_asset.usage_type = UsageType.PUBLIC.value
    context.child_asset.public_object_id = context.public_object.id
    context.child_asset.holder_user_id = None

    with pytest.raises(BusinessException):
        require_personal_assets(
            [context.main_asset, context.child_asset], context.employee.id
        )
    with pytest.raises(BusinessException):
        require_public_assets([context.main_asset, context.child_asset])


def _configure_personal_asset(context: Any) -> Asset:
    asset = context.main_asset
    asset.status = AssetStatus.IN_USE.value
    asset.usage_type = UsageType.PERSONAL.value
    asset.holder_user_id = context.employee.id
    asset.public_object_id = None
    return asset


def test_personal_asset_validation_accepts_valid_batch(app) -> None:
    context = seed_usage_return_context()
    assets = [context.main_asset, context.child_asset]
    for asset in assets:
        asset.status = AssetStatus.IN_USE.value
        asset.usage_type = UsageType.PERSONAL.value
        asset.holder_user_id = context.employee.id
        asset.public_object_id = None

    assert require_personal_assets(assets, context.employee.id) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda asset, context: setattr(asset, "status", AssetStatus.IDLE.value),
        lambda asset, context: setattr(asset, "usage_type", UsageType.PUBLIC.value),
        lambda asset, context: setattr(asset, "holder_user_id", context.manager.id),
        lambda asset, context: setattr(
            asset, "public_object_id", context.public_object.id
        ),
    ],
    ids=[
        "wrong-status",
        "wrong-usage-type",
        "wrong-holder",
        "unexpected-public-object",
    ],
)
def test_personal_asset_validation_isolates_each_required_predicate(
    app,
    mutate: Callable[[Asset, Any], None],
) -> None:
    context = seed_usage_return_context()
    asset = _configure_personal_asset(context)
    mutate(asset, context)

    with pytest.raises(BusinessException):
        require_personal_assets([asset], context.employee.id)


def _configure_public_asset(context: Any) -> Asset:
    asset = context.main_asset
    asset.status = AssetStatus.IN_USE.value
    asset.usage_type = UsageType.PUBLIC.value
    asset.public_object_id = context.public_object.id
    asset.holder_user_id = None
    return asset


def test_public_asset_validation_accepts_valid_batch(app) -> None:
    context = seed_usage_return_context()
    assets = [context.main_asset, context.child_asset]
    for asset in assets:
        asset.status = AssetStatus.IN_USE.value
        asset.usage_type = UsageType.PUBLIC.value
        asset.public_object_id = context.public_object.id
        asset.holder_user_id = None

    assert require_public_assets(assets) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda asset, context: setattr(asset, "status", AssetStatus.IDLE.value),
        lambda asset, context: setattr(asset, "usage_type", UsageType.PERSONAL.value),
        lambda asset, context: setattr(asset, "public_object_id", None),
        lambda asset, context: setattr(asset, "holder_user_id", context.employee.id),
    ],
    ids=[
        "wrong-status",
        "wrong-usage-type",
        "missing-public-object",
        "unexpected-holder",
    ],
)
def test_public_asset_validation_isolates_each_required_predicate(
    app,
    mutate: Callable[[Asset, Any], None],
) -> None:
    context = seed_usage_return_context()
    asset = _configure_public_asset(context)
    mutate(asset, context)

    with pytest.raises(BusinessException):
        require_public_assets([asset])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda context: setattr(context.employee, "enabled", False), "用户已停用"),
        (
            lambda context: setattr(
                context.organization, "status", RecordStatus.DISABLED.value
            ),
            "所属组织已停用",
        ),
    ],
)
def test_personal_target_reports_each_validation_failure(
    app, mutate: Callable[[Any], None], message: str
) -> None:
    context = seed_usage_return_context()
    mutate(context)
    db.session.flush()

    with pytest.raises(BusinessException) as error:
        require_personal_target(context.employee.id)

    assert error.value.message == message


def test_personal_target_accepts_enabled_user_with_enabled_department(app) -> None:
    context = seed_usage_return_context()

    assert require_personal_target(context.employee.id) is context.employee


def test_personal_target_rejects_missing_user(app) -> None:
    context = seed_usage_return_context()

    with pytest.raises(BusinessException) as error:
        require_personal_target(context.employee.id + 1000)

    assert error.value.message == "用户不存在"


def test_public_target_rejects_missing_and_disabled_object(app) -> None:
    context = seed_usage_return_context()

    with pytest.raises(BusinessException):
        require_public_target(context.public_object.id + 1000)

    context.public_object.status = RecordStatus.DISABLED.value
    db.session.flush()
    with pytest.raises(BusinessException):
        require_public_target(context.public_object.id)


def test_public_target_accepts_enabled_object(app) -> None:
    context = seed_usage_return_context()

    assert require_public_target(context.public_object.id) is context.public_object


def test_location_rejects_disabled_and_nonselectable_records(app) -> None:
    context = seed_usage_return_context()

    context.location.status = RecordStatus.DISABLED.value
    db.session.flush()
    with pytest.raises(BusinessException):
        require_location(context.location.id)

    context.location.status = RecordStatus.ENABLED.value
    context.location.is_selectable = False
    db.session.flush()
    with pytest.raises(BusinessException):
        require_location(context.location.id)


def test_location_accepts_enabled_selectable_record(app) -> None:
    context = seed_usage_return_context()

    assert require_location(context.location.id) is context.location


def _operation_with_snapshots() -> tuple[OperationRequest, list[OperationRequestAsset]]:
    context = seed_usage_return_context()
    now = utc_now()
    operation = OperationRequest(
        request_no="UR-REQUEST-1",
        operation_type=OperationType.PERSONAL_USE.value,
        applicant_id=context.employee.id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        execution_error="UR execution error",
        external_instance_id="UR-EXTERNAL-1",
        submitted_at=now,
        approved_at=now + timedelta(seconds=1),
        executed_at=now + timedelta(seconds=2),
        terminated_at=now + timedelta(seconds=3),
        terminated_by=context.manager.id,
        termination_reason="UR termination reason",
        created_at=now + timedelta(seconds=4),
        updated_at=now + timedelta(seconds=5),
    )
    db.session.add(operation)
    db.session.flush()
    rows = [
        OperationRequestAsset(
            operation_request_id=operation.id,
            asset_id=asset.id,
            asset_code_snapshot=asset.asset_code,
            asset_name_snapshot=asset.asset_name,
            asset_status_snapshot=asset.status,
            asset_version_snapshot=asset.version,
            organization_id_snapshot=asset.organization_id,
            holder_snapshot={"id": context.employee.id, "amount": "10.00"},
            location_snapshot={"id": context.location.id},
            before_data={"status": asset.status, "repair_cost": "20.00"},
            target_data={"status": AssetStatus.IN_USE.value, "amount": "30.00"},
        )
        for asset in (context.child_asset, context.main_asset)
    ]
    db.session.add_all(rows)
    db.session.flush()
    return operation, rows


def _assert_no_models(value: Any) -> None:
    assert not isinstance(value, db.Model)
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_models(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_models(item)


def test_operation_assets_are_stable_and_serialization_is_authorized_dict(app) -> None:
    operation, rows = _operation_with_snapshots()
    actor_id = operation.applicant_id

    ordered = operation_assets(operation.id)
    result = serialize_operation(
        operation,
        actor_id,
        feature_data={"target_user_id": actor_id, "amount": "99.00"},
        allowed_actions=("APPROVE", "WITHDRAW"),
    )

    assert [row.asset_id for row in ordered] == sorted(row.asset_id for row in rows)
    assert isinstance(result, dict)
    assert result["id"] == operation.id
    assert result["request_no"] == "UR-REQUEST-1"
    assert result["operation_type"] == OperationType.PERSONAL_USE.value
    assert result["applicant_id"] == actor_id
    assert result["approval_channel"] == ApprovalChannel.INTERNAL.value
    assert (
        result["approval_execution_mode"]
        == ApprovalExecutionMode.AUTO_ON_APPROVAL.value
    )
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    assert result["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert result["execution_error"] == "UR execution error"
    assert result["external_instance_id"] == "UR-EXTERNAL-1"
    assert result["submitted_at"] == operation.submitted_at
    assert result["approved_at"] == operation.approved_at
    assert result["executed_at"] == operation.executed_at
    assert result["terminated_at"] == operation.terminated_at
    assert result["terminated_by"] == operation.terminated_by
    assert result["termination_reason"] == operation.termination_reason
    assert result["created_at"] == operation.created_at
    assert result["updated_at"] == operation.updated_at
    ordered_rows = sorted(rows, key=lambda row: row.asset_id)
    assert result["assets"] == [
        {
            "asset_id": row.asset_id,
            "asset_code": row.asset_code_snapshot,
            "asset_name": row.asset_name_snapshot,
            "asset_status": row.asset_status_snapshot,
            "asset_version": row.asset_version_snapshot,
            "organization_id": row.organization_id_snapshot,
            "holder_snapshot": {"id": actor_id},
            "location_snapshot": row.location_snapshot,
            "before_data": {"status": row.asset_status_snapshot},
            "target_data": {"status": AssetStatus.IN_USE.value},
        }
        for row in ordered_rows
    ]
    assert result["feature"] == {"target_user_id": actor_id}
    assert result["allowed_actions"] == ["APPROVE", "WITHDRAW"]
    assert "amount" not in result["assets"][0]["holder_snapshot"]
    assert "repair_cost" not in result["assets"][0]["before_data"]
    assert "amount" not in result["assets"][0]["target_data"]
    _assert_no_models(result)


def test_serialization_preserves_amounts_for_authorized_actor(app) -> None:
    operation, _rows = _operation_with_snapshots()
    grant_permissions(operation.applicant_id, "asset:amount:view")

    result = serialize_operation(
        operation,
        operation.applicant_id,
        feature_data={"amount": "99.00"},
    )

    assert result["feature"]["amount"] == "99.00"
    assert result["assets"][0]["holder_snapshot"]["amount"] == "10.00"


@pytest.mark.parametrize("can_view_amount", [False, True])
def test_serialization_deep_copies_json_with_and_without_amount_permission(
    app,
    can_view_amount: bool,
) -> None:
    operation, rows = _operation_with_snapshots()
    row = rows[0]
    row.holder_snapshot = {
        "id": operation.applicant_id,
        "details": {"labels": ["holder"]},
        "amount": "10.00",
    }
    row.location_snapshot = {
        "id": 1,
        "details": {"labels": ["location"]},
    }
    row.before_data = {
        "details": {"labels": ["before"]},
        "repair_cost": "20.00",
    }
    row.target_data = {
        "details": {"labels": ["target"]},
        "amount": "30.00",
    }
    feature_data = {
        "details": {"labels": ["feature"]},
        "amount": "40.00",
    }
    db.session.flush()
    if can_view_amount:
        grant_permissions(operation.applicant_id, "asset:amount:view")

    result = serialize_operation(
        operation,
        operation.applicant_id,
        feature_data=feature_data,
    )
    serialized = next(
        item for item in result["assets"] if item["asset_id"] == row.asset_id
    )

    assert ("amount" in serialized["holder_snapshot"]) is can_view_amount
    assert ("repair_cost" in serialized["before_data"]) is can_view_amount
    assert ("amount" in serialized["target_data"]) is can_view_amount
    assert ("amount" in result["feature"]) is can_view_amount
    serialized["holder_snapshot"]["details"]["labels"].append("changed")
    serialized["location_snapshot"]["details"]["labels"].append("changed")
    serialized["before_data"]["details"]["labels"].append("changed")
    serialized["target_data"]["details"]["labels"].append("changed")
    result["feature"]["details"]["labels"].append("changed")

    assert row.holder_snapshot["details"]["labels"] == ["holder"]
    assert row.location_snapshot["details"]["labels"] == ["location"]
    assert row.before_data["details"]["labels"] == ["before"]
    assert row.target_data["details"]["labels"] == ["target"]
    assert feature_data["details"]["labels"] == ["feature"]


@pytest.mark.parametrize("unsupported_kind", ["tuple", "model"])
def test_serialization_rejects_unsupported_json_values(
    app,
    unsupported_kind: str,
) -> None:
    operation, rows = _operation_with_snapshots()
    unsupported: object = ("not", "json")
    if unsupported_kind == "model":
        unsupported = rows[0]

    with pytest.raises(TypeError, match="unsupported JSON value"):
        serialize_operation(
            operation,
            operation.applicant_id,
            feature_data={"unsupported": unsupported},
        )


def test_grant_permissions_reuses_existing_permission_and_links(app) -> None:
    context = seed_usage_return_context()
    existing = Permission(
        code="usage-return:view",
        name="Existing Usage Return Permission",
        module="usage-return",
    )
    db.session.add(existing)
    db.session.flush()

    grant_permissions(
        context.employee,
        "usage-return:view",
        "usage-return:create",
        "usage-return:view",
    )
    grant_permissions(context.employee, "usage-return:view")

    assert Permission.query.filter_by(code="usage-return:view").count() == 1
    role = Role.query.filter_by(code=f"UR-ALL-{context.employee.id}").one()
    assert role.enabled is True
    assert role.data_scope == DataScope.ALL.value
    permission_ids = {
        link.permission_id
        for link in RolePermission.query.filter_by(role_id=role.id).all()
    }
    assert existing.id in permission_ids
    assert (
        UserRole.query.filter_by(user_id=context.employee.id, role_id=role.id).count()
        == 1
    )


def test_seed_context_creates_complete_one_level_asset_relationship(app) -> None:
    context = seed_usage_return_context()

    assert context.organization.code.startswith("UR-")
    assert context.location.code.startswith("UR-")
    assert context.return_location.code.startswith("UR-")
    assert context.manager.username.startswith("UR-")
    assert context.employee.username.startswith("UR-")
    assert context.manager.organization_id == context.organization.id
    assert context.employee.organization_id == context.organization.id
    assert context.public_object.code.startswith("UR-")
    assert context.main_asset.status == AssetStatus.IDLE.value
    assert context.child_asset.status == AssetStatus.IDLE.value
    assert context.child_asset.parent_asset_id == context.main_asset.id
    assert context.main_asset.asset_code.startswith("UR-")
    assert context.child_asset.asset_code.startswith("UR-")
    assert all(
        value is not None
        for value in (
            context.main_asset.category_id,
            context.main_asset.unit_id,
            context.main_asset.original_amount,
            context.main_asset.purchase_date,
            context.main_asset.manager_id,
            context.main_asset.source_id,
            context.main_asset.location_id,
        )
    )


def test_register_usage_return_handlers_imports_lazily_and_skips_existing(
    monkeypatch,
) -> None:
    def handler_class(name: str, operation_type: str) -> type:
        return type(name, (), {"operation_type": operation_type})

    module = ModuleType("app.operations.asset_usage_return_handlers")
    module.PersonalUsageHandler = handler_class(
        "PersonalUsageHandler", "CUSTOM_PERSONAL_USE"
    )
    module.PublicUsageHandler = handler_class(
        "PublicUsageHandler", OperationType.PUBLIC_USE.value
    )
    module.PersonalReturnHandler = handler_class(
        "PersonalReturnHandler", OperationType.PERSONAL_RETURN.value
    )
    module.PublicReturnHandler = handler_class(
        "PublicReturnHandler", OperationType.PUBLIC_RETURN.value
    )
    monkeypatch.setitem(
        sys.modules,
        "app.operations.asset_usage_return_handlers",
        module,
    )
    registry = OperationHandlerRegistry()
    existing = module.PersonalUsageHandler()
    registry.register(existing)
    monkeypatch.setattr(
        usage_return_fixtures,
        "operation_handler_registry",
        registry,
    )

    usage_return_fixtures.register_usage_return_handlers()
    usage_return_fixtures.register_usage_return_handlers()

    assert registry.get("CUSTOM_PERSONAL_USE") is existing
    assert not registry.contains(OperationType.PERSONAL_USE.value)
    for operation_type in (
        OperationType.PUBLIC_USE.value,
        OperationType.PERSONAL_RETURN.value,
        OperationType.PUBLIC_RETURN.value,
    ):
        assert registry.contains(operation_type)
