"""Read-only one-level main/attachment asset expansion."""

from __future__ import annotations

from collections.abc import Sequence

from app.common import BusinessException, ResultCode
from app.models import Asset
from app.repositories.asset_repository import asset_repository


def find_direct_children(parent_ids: Sequence[int]) -> list[Asset]:
    return asset_repository.find_direct_children(parent_ids)


def expand_with_direct_children(asset_ids: Sequence[int]) -> list[Asset]:
    requested_ids = sorted(set(asset_ids))
    roots = asset_repository.find_many_ordered(requested_ids)
    if len(roots) != len(requested_ids):
        raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
    children = find_direct_children(requested_ids)
    grandchildren = find_direct_children([asset.id for asset in children])
    child_parent_ids = {asset.parent_asset_id for asset in children}
    nested_root = any(
        asset.parent_asset_id is not None and asset.id in child_parent_ids
        for asset in roots
    )
    if grandchildren or nested_root:
        raise BusinessException("主附资产只允许一层关系")
    unique_assets = {asset.id: asset for asset in [*roots, *children]}
    return sorted(unique_assets.values(), key=lambda asset: asset.id)


__all__ = ["expand_with_direct_children", "find_direct_children"]
