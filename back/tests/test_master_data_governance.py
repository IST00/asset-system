from __future__ import annotations

from app.enums import DataScope
from app.extensions import db
from app.models import OperationLog, Permission, Role, RolePermission, User, UserRole
from app.security.passwords import hash_password


_PERMISSIONS = (
    "location:view",
    "location:manage",
    "location:delete",
    "asset-category:view",
    "asset-category:manage",
    "asset-category:delete",
    "unit:view",
    "unit:manage",
)


def _headers(client, *, super_admin: bool = True) -> tuple[User, dict[str, str]]:
    suffix = "super" if super_admin else "ordinary"
    user = User(
        username=f"master-{suffix}", password=hash_password("admin123"), enabled=True
    )
    role = Role(
        code="SUPER_ADMIN" if super_admin else "MASTER_DELETE_ADMIN",
        name="超级管理员" if super_admin else "基础资料删除管理员",
        data_scope=DataScope.ALL.value,
        built_in=super_admin,
    )
    permissions = [
        Permission(code=code, name=code, module=code.split(":")[0])
        for code in _PERMISSIONS
    ]
    db.session.add_all([user, role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "admin123"},
    ).get_json()["data"]["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _create_location(client, headers, name: str, parent_id: int | None = None) -> dict:
    response = client.post(
        "/api/v1/locations",
        headers=headers,
        json={"name": name, "parent_id": parent_id, "is_selectable": True},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def _create_unit(client, headers) -> dict:
    return client.post(
        "/api/v1/units", headers=headers, json={"code": "UNIT", "name": "台"}
    ).get_json()["data"]


def _create_category(
    client, headers, unit_id: int, code: str, name: str, parent_id: int | None = None
) -> dict:
    return client.post(
        "/api/v1/asset-categories",
        headers=headers,
        json={
            "code": code,
            "name": name,
            "parent_id": parent_id,
            "service_life_months": 36,
            "default_unit_id": unit_id,
        },
    ).get_json()["data"]


def test_location_codes_are_generated_and_never_reused_after_delete(client) -> None:
    actor, headers = _headers(client)
    first = _create_location(client, headers, "一号地点")
    second = _create_location(client, headers, "二号地点")
    assert first["code"] == "LOC000001"
    assert second["code"] == "LOC000002"

    impact = client.get(
        f"/api/v1/locations/{second['id']}/delete-impact", headers=headers
    ).get_json()["data"]
    assert impact["can_delete"] is True
    deleted = client.post(
        f"/api/v1/locations/{second['id']}/delete",
        headers=headers,
        json={
            "version": impact["version"],
            "reason": "误建地点",
            "confirmed": True,
        },
    ).get_json()["data"]
    assert deleted["deleted"] is True
    third = _create_location(client, headers, "三号地点")
    assert third["code"] == "LOC000003"

    audit = db.session.query(OperationLog).filter_by(action="LOCATION_DELETE").one()
    assert audit.operator_id == actor.id
    assert audit.reason == "误建地点"
    assert audit.before_data is not None
    assert audit.before_data["code"] == "LOC000002"


def test_location_and_category_delete_impact_checks_children_and_history(
    client,
) -> None:
    actor, headers = _headers(client)
    parent = _create_location(client, headers, "总部")
    child = _create_location(client, headers, "机房", parent["id"])
    parent_impact = client.get(
        f"/api/v1/locations/{parent['id']}/delete-impact", headers=headers
    ).get_json()["data"]
    assert parent_impact["can_delete"] is False
    assert (
        next(item for item in parent_impact["references"] if item["key"] == "children")[
            "count"
        ]
        == 1
    )

    unit = _create_unit(client, headers)
    category = _create_category(client, headers, unit["id"], "900", "历史分类")
    db.session.add(
        OperationLog(
            action="TEST_HISTORY",
            resource_type="test",
            resource_id="1",
            operator_id=actor.id,
            before_data={"location_id": child["id"]},
            after_data={"category_id": category["id"]},
        )
    )
    db.session.commit()

    location_impact = client.get(
        f"/api/v1/locations/{child['id']}/delete-impact", headers=headers
    ).get_json()["data"]
    category_impact = client.get(
        f"/api/v1/asset-categories/{category['id']}/delete-impact", headers=headers
    ).get_json()["data"]
    assert location_impact["can_delete"] is False
    assert category_impact["can_delete"] is False
    assert (
        next(
            item
            for item in location_impact["references"]
            if item["key"] == "operation_logs"
        )["count"]
        == 1
    )
    assert (
        next(
            item
            for item in category_impact["references"]
            if item["key"] == "operation_logs"
        )["count"]
        == 1
    )


def test_leaf_category_can_be_deleted_with_reason_and_confirmation(client) -> None:
    actor, headers = _headers(client)
    unit = _create_unit(client, headers)
    category = _create_category(client, headers, unit["id"], "901", "误建分类")
    impact = client.get(
        f"/api/v1/asset-categories/{category['id']}/delete-impact", headers=headers
    ).get_json()["data"]
    assert impact["can_delete"] is True

    missing_confirmation = client.post(
        f"/api/v1/asset-categories/{category['id']}/delete",
        headers=headers,
        json={"version": category["version"], "reason": "误建分类", "confirmed": False},
    )
    assert missing_confirmation.status_code == 400

    deleted = client.post(
        f"/api/v1/asset-categories/{category['id']}/delete",
        headers=headers,
        json={"version": category["version"], "reason": "误建分类", "confirmed": True},
    ).get_json()["data"]
    assert deleted["deleted"] is True
    audit = (
        db.session.query(OperationLog).filter_by(action="ASSET_CATEGORY_DELETE").one()
    )
    assert audit.operator_id == actor.id
    assert audit.reason == "误建分类"


def test_delete_permission_still_requires_super_admin_role(client) -> None:
    _actor, headers = _headers(client, super_admin=False)
    location = _create_location(client, headers, "普通管理员地点")
    response = client.get(
        f"/api/v1/locations/{location['id']}/delete-impact", headers=headers
    )
    assert response.get_json()["code"] == 403
    assert "超级管理员" in response.get_json()["message"]
