"""HTTP boundary for personal and public asset-usage requests."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.asset_usage_return import (
    PersonalBorrowCreateSchema,
    PersonalUsageCreateSchema,
    SelfPersonalBorrowCreateSchema,
    SelfPersonalUsageCreateSchema,
    PublicBorrowCreateSchema,
    PublicUsageCreateSchema,
    UsageReturnPageQuerySchema,
    UsageFulfillmentRemarkSchema,
    UsageIssueSchema,
    UsageSignRefusalSchema,
    BorrowReturnRequestSchema,
    BorrowExtensionCreateSchema,
    BorrowExtensionReviewSchema,
)
from app.security import current_user_id
from app.services import (
    asset_borrow_extension_service,
    asset_usage_fulfillment_service,
    asset_usage_service,
)

bp = Blueprint(
    "asset_usage",
    __name__,
    url_prefix="/api/v1/asset-usage-requests",
)

_personal_schema = PersonalUsageCreateSchema()
_personal_direct_schema = PersonalUsageCreateSchema()
_personal_borrow_schema = PersonalBorrowCreateSchema()
_personal_borrow_direct_schema = PersonalBorrowCreateSchema()
_self_personal_schema = SelfPersonalUsageCreateSchema()
_self_personal_borrow_schema = SelfPersonalBorrowCreateSchema()
_public_schema = PublicUsageCreateSchema()
_public_borrow_schema = PublicBorrowCreateSchema()
_page_schema = UsageReturnPageQuerySchema()
_issue_schema = UsageIssueSchema()
_fulfillment_remark_schema = UsageFulfillmentRemarkSchema()
_sign_refusal_schema = UsageSignRefusalSchema()
_borrow_return_request_schema = BorrowReturnRequestSchema()
_borrow_extension_create_schema = BorrowExtensionCreateSchema()
_borrow_extension_review_schema = BorrowExtensionReviewSchema()


@bp.get("/self-service-references")
@jwt_required()
def self_service_references() -> dict:
    data = asset_usage_service.self_service_references(current_user_id())
    return Result.success(data).to_dict()


@bp.get("/my-assets")
@jwt_required()
def my_assets() -> dict:
    data = asset_usage_service.my_assets(current_user_id())
    return Result.success(data).to_dict()


@bp.post("/personal")
@jwt_required()
def submit_personal() -> dict:
    payload = _personal_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_personal(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/personal-direct")
@jwt_required()
def submit_personal_direct() -> dict:
    payload = _personal_direct_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_personal_direct(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/personal-self")
@jwt_required()
def submit_personal_self() -> dict:
    payload = _self_personal_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_personal_self(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/personal-borrow-self")
@jwt_required()
def submit_personal_borrow_self() -> dict:
    payload = _self_personal_borrow_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_personal_borrow_self(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/public")
@jwt_required()
def submit_public() -> dict:
    payload = _public_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_public(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/personal-borrow")
@jwt_required()
def submit_personal_borrow() -> dict:
    payload = _personal_borrow_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_personal_borrow(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/personal-borrow-direct")
@jwt_required()
def submit_personal_borrow_direct() -> dict:
    payload = _personal_borrow_direct_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_personal_borrow_direct(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/public-borrow")
@jwt_required()
def submit_public_borrow() -> dict:
    payload = _public_borrow_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_public_borrow(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.get("")
@jwt_required()
def page() -> dict:
    query = _page_schema.load(request.args.to_dict())
    data = asset_usage_service.page(
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
    ).to_dict()
    return Result.success(data).to_dict()


@bp.get("/<int:operation_request_id>")
@jwt_required()
def get(operation_request_id: int) -> dict:
    data = asset_usage_service.get(operation_request_id, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/<int:operation_request_id>/issue")
@jwt_required()
def issue(operation_request_id: int) -> dict:
    payload = _issue_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_fulfillment_service.issue(
        operation_request_id,
        current_user_id(),
        payload["asset_ids"],
        payload["region_id"],
        payload["location_id"],
        payload.get("remark"),
    )
    return Result.success(data).to_dict()


@bp.get("/<int:operation_request_id>/issue-candidates")
@jwt_required()
def issue_candidates(operation_request_id: int) -> dict:
    data = asset_usage_fulfillment_service.issue_candidates(
        operation_request_id,
        current_user_id(),
    )
    return Result.success(data).to_dict()


@bp.post("/<int:operation_request_id>/sign")
@jwt_required()
def sign(operation_request_id: int) -> dict:
    payload = _fulfillment_remark_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_fulfillment_service.sign(
        operation_request_id,
        current_user_id(),
        payload.get("remark"),
    )
    return Result.success(data).to_dict()


@bp.post("/<int:operation_request_id>/refuse-sign")
@jwt_required()
def refuse_sign(operation_request_id: int) -> dict:
    payload = _sign_refusal_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_fulfillment_service.refuse_sign(
        operation_request_id,
        current_user_id(),
        payload["remark"],
    )
    return Result.success(data).to_dict()


@bp.get("/borrow-extensions/pending")
@jwt_required()
def list_pending_borrow_extensions() -> dict:
    return Result.success(
        asset_borrow_extension_service.list_pending(current_user_id())
    ).to_dict()


@bp.get("/<int:operation_request_id>/extensions")
@jwt_required()
def list_borrow_extensions(operation_request_id: int) -> dict:
    data = asset_borrow_extension_service.list_for_request(
        operation_request_id, current_user_id()
    )
    return Result.success(data).to_dict()


@bp.post("/<int:operation_request_id>/extensions")
@jwt_required()
def create_borrow_extension(operation_request_id: int) -> dict:
    payload = _borrow_extension_create_schema.load(request.get_json(silent=True) or {})
    data = asset_borrow_extension_service.create(
        operation_request_id,
        current_user_id(),
        payload["requested_expected_return_at"],
        payload["reason"],
    )
    return Result.success(data).to_dict()


@bp.post("/borrow-extensions/<int:extension_id>/approve")
@jwt_required()
def approve_borrow_extension(extension_id: int) -> dict:
    payload = _borrow_extension_review_schema.load(request.get_json(silent=True) or {})
    data = asset_borrow_extension_service.approve(
        extension_id, current_user_id(), payload.get("opinion")
    )
    return Result.success(data).to_dict()


@bp.post("/borrow-extensions/<int:extension_id>/reject")
@jwt_required()
def reject_borrow_extension(extension_id: int) -> dict:
    payload = _borrow_extension_review_schema.load(request.get_json(silent=True) or {})
    data = asset_borrow_extension_service.reject(
        extension_id, current_user_id(), payload.get("opinion") or ""
    )
    return Result.success(data).to_dict()


@bp.post("/<int:operation_request_id>/request-return")
@jwt_required()
def request_borrow_return(operation_request_id: int) -> dict:
    payload = _borrow_return_request_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_fulfillment_service.request_return(
        operation_request_id,
        current_user_id(),
        payload["reason"],
    )
    return Result.success(data).to_dict()
