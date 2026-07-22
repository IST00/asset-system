"""Persistence queries for asset usage and return requests."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import and_, exists, false, func, or_, select, true
from sqlalchemy.sql.elements import ColumnElement

from app.enums import OperationType
from app.extensions import db
from app.models.asset_usage_return import (
    AssetReturnItem,
    AssetReturnRequest,
    AssetUsageRequest,
)
from app.models.operation import OperationRequestAsset
from app.models.workflow import OperationRequest
from app.repositories.base import BaseRepository, Page


def _manager_scope_filter(
    *,
    can_manage: bool,
    organization_ids: set[int] | None,
) -> ColumnElement[bool]:
    if not can_manage:
        return false()
    if organization_ids is None:
        return true()
    if not organization_ids:
        return false()
    has_asset = exists(
        select(1)
        .select_from(OperationRequestAsset)
        .where(OperationRequestAsset.operation_request_id == OperationRequest.id)
    )
    out_of_scope_asset = exists(
        select(1)
        .select_from(OperationRequestAsset)
        .where(
            OperationRequestAsset.operation_request_id == OperationRequest.id,
            OperationRequestAsset.organization_id_snapshot.not_in(
                sorted(organization_ids)
            ),
        )
    )
    return and_(has_asset, ~out_of_scope_asset)


def _usage_visibility_filter(
    *,
    actor_id: int,
    can_manage: bool,
    organization_ids: set[int] | None,
) -> ColumnElement[bool]:
    return and_(
        OperationRequest.operation_type.in_(
            (
                OperationType.PERSONAL_USE.value,
                OperationType.PUBLIC_USE.value,
            )
        ),
        or_(
            OperationRequest.applicant_id == actor_id,
            and_(
                OperationRequest.operation_type == OperationType.PERSONAL_USE.value,
                AssetUsageRequest.target_user_id == actor_id,
            ),
            _manager_scope_filter(
                can_manage=can_manage,
                organization_ids=organization_ids,
            ),
        ),
    )


def _return_visibility_filter(
    *,
    actor_id: int,
    can_manage: bool,
    organization_ids: set[int] | None,
) -> ColumnElement[bool]:
    return and_(
        OperationRequest.operation_type.in_(
            (
                OperationType.PERSONAL_RETURN.value,
                OperationType.PUBLIC_RETURN.value,
            )
        ),
        or_(
            OperationRequest.applicant_id == actor_id,
            _manager_scope_filter(
                can_manage=can_manage,
                organization_ids=organization_ids,
            ),
        ),
    )


def find_operation_assets(
    operation_request_ids: Sequence[int],
) -> list[OperationRequestAsset]:
    request_ids = sorted(set(operation_request_ids))
    if not request_ids:
        return []
    statement = (
        select(OperationRequestAsset)
        .where(OperationRequestAsset.operation_request_id.in_(request_ids))
        .order_by(
            OperationRequestAsset.operation_request_id.asc(),
            OperationRequestAsset.asset_id.asc(),
        )
    )
    return list(db.session.scalars(statement).all())


class AssetUsageRequestRepository(BaseRepository[AssetUsageRequest]):
    def __init__(self) -> None:
        super().__init__(AssetUsageRequest)

    def find_by_operation(self, operation_request_id: int) -> AssetUsageRequest | None:
        statement = select(AssetUsageRequest).where(
            AssetUsageRequest.operation_request_id == operation_request_id
        )
        return db.session.scalar(statement)

    def find_visible_usage(
        self,
        *,
        operation_request_id: int,
        actor_id: int,
        can_manage: bool,
        organization_ids: set[int] | None,
    ) -> tuple[OperationRequest, AssetUsageRequest] | None:
        statement = (
            select(OperationRequest, AssetUsageRequest)
            .join(
                AssetUsageRequest,
                AssetUsageRequest.operation_request_id == OperationRequest.id,
            )
            .where(
                OperationRequest.id == operation_request_id,
                _usage_visibility_filter(
                    actor_id=actor_id,
                    can_manage=can_manage,
                    organization_ids=organization_ids,
                ),
            )
        )
        return db.session.execute(statement).tuples().one_or_none()

    def page_usage(
        self,
        *,
        actor_id: int,
        can_manage: bool,
        organization_ids: set[int] | None,
        page: int,
        size: int,
    ) -> Page[tuple[OperationRequest, AssetUsageRequest]]:
        visibility_filter = _usage_visibility_filter(
            actor_id=actor_id,
            can_manage=can_manage,
            organization_ids=organization_ids,
        )
        total_statement = (
            select(func.count(func.distinct(OperationRequest.id)))
            .select_from(OperationRequest)
            .join(
                AssetUsageRequest,
                AssetUsageRequest.operation_request_id == OperationRequest.id,
            )
            .where(visibility_filter)
        )
        rows_statement = (
            select(OperationRequest, AssetUsageRequest)
            .join(
                AssetUsageRequest,
                AssetUsageRequest.operation_request_id == OperationRequest.id,
            )
            .where(visibility_filter)
            .order_by(OperationRequest.created_at.desc(), OperationRequest.id.desc())
            .limit(size)
            .offset(page * size)
        )
        total = int(db.session.scalar(total_statement) or 0)
        items = list(db.session.execute(rows_statement).tuples().all())
        return Page(items=items, total=total, page=page, size=size)


class AssetReturnRequestRepository(BaseRepository[AssetReturnRequest]):
    def __init__(self) -> None:
        super().__init__(AssetReturnRequest)

    def find_by_operation(self, operation_request_id: int) -> AssetReturnRequest | None:
        statement = select(AssetReturnRequest).where(
            AssetReturnRequest.operation_request_id == operation_request_id
        )
        return db.session.scalar(statement)

    def find_visible_return(
        self,
        *,
        operation_request_id: int,
        actor_id: int,
        can_manage: bool,
        organization_ids: set[int] | None,
    ) -> tuple[OperationRequest, AssetReturnRequest] | None:
        statement = (
            select(OperationRequest, AssetReturnRequest)
            .join(
                AssetReturnRequest,
                AssetReturnRequest.operation_request_id == OperationRequest.id,
            )
            .where(
                OperationRequest.id == operation_request_id,
                _return_visibility_filter(
                    actor_id=actor_id,
                    can_manage=can_manage,
                    organization_ids=organization_ids,
                ),
            )
        )
        return db.session.execute(statement).tuples().one_or_none()

    def page_returns(
        self,
        *,
        actor_id: int,
        can_manage: bool,
        organization_ids: set[int] | None,
        page: int,
        size: int,
    ) -> Page[tuple[OperationRequest, AssetReturnRequest]]:
        visibility_filter = _return_visibility_filter(
            actor_id=actor_id,
            can_manage=can_manage,
            organization_ids=organization_ids,
        )
        total_statement = (
            select(func.count(func.distinct(OperationRequest.id)))
            .select_from(OperationRequest)
            .join(
                AssetReturnRequest,
                AssetReturnRequest.operation_request_id == OperationRequest.id,
            )
            .where(visibility_filter)
        )
        rows_statement = (
            select(OperationRequest, AssetReturnRequest)
            .join(
                AssetReturnRequest,
                AssetReturnRequest.operation_request_id == OperationRequest.id,
            )
            .where(visibility_filter)
            .order_by(OperationRequest.created_at.desc(), OperationRequest.id.desc())
            .limit(size)
            .offset(page * size)
        )
        total = int(db.session.scalar(total_statement) or 0)
        items = list(db.session.execute(rows_statement).tuples().all())
        return Page(items=items, total=total, page=page, size=size)


class AssetReturnItemRepository(BaseRepository[AssetReturnItem]):
    def __init__(self) -> None:
        super().__init__(AssetReturnItem)

    def find_by_operation(self, operation_request_id: int) -> list[AssetReturnItem]:
        statement = (
            select(AssetReturnItem)
            .join(
                OperationRequestAsset,
                AssetReturnItem.operation_request_asset_id == OperationRequestAsset.id,
            )
            .where(OperationRequestAsset.operation_request_id == operation_request_id)
            .order_by(AssetReturnItem.operation_request_asset_id.asc())
        )
        return list(db.session.scalars(statement).all())

    def find_by_request_asset_ids(self, ids: Sequence[int]) -> list[AssetReturnItem]:
        request_asset_ids = sorted(set(ids))
        if not request_asset_ids:
            return []
        statement = (
            select(AssetReturnItem)
            .where(AssetReturnItem.operation_request_asset_id.in_(request_asset_ids))
            .order_by(AssetReturnItem.operation_request_asset_id.asc())
        )
        return list(db.session.scalars(statement).all())


asset_usage_request_repository = AssetUsageRequestRepository()
asset_return_request_repository = AssetReturnRequestRepository()
asset_return_item_repository = AssetReturnItemRepository()


__all__ = [
    "AssetReturnItemRepository",
    "AssetReturnRequestRepository",
    "AssetUsageRequestRepository",
    "asset_return_item_repository",
    "asset_return_request_repository",
    "asset_usage_request_repository",
    "find_operation_assets",
]
