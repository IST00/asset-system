"""Central asset functional-permission and data-scope access rules."""

from sqlalchemy import ColumnElement, false, or_

from app.common import BusinessException, ResultCode
from app.enums import DataScope
from app.models import Asset
from app.repositories import asset_repository
from app.services import permission_service


def access_filter(actor_id: int) -> ColumnElement[bool]:
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids is None:
        return Asset.id.is_not(None)

    conditions: list[ColumnElement[bool]] = []
    if organization_ids:
        conditions.append(Asset.organization_id.in_(organization_ids))
    if DataScope.SELF.value in permission_service.get_data_scopes(actor_id):
        # For employee-facing asset views, SELF means assets held by the actor.
        # Managed assets remain visible only through broader administrative scopes.
        conditions.append(Asset.holder_user_id == actor_id)
    return or_(*conditions) if conditions else false()


def get_accessible(
    asset_id: int,
    actor_id: int,
    permission_code: str = "asset:view",
) -> Asset:
    permission_service.require_permission(actor_id, permission_code)
    asset = asset_repository.find_accessible(asset_id, access_filter(actor_id))
    if asset is None:
        raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
    return asset


__all__ = ["access_filter", "get_accessible"]
