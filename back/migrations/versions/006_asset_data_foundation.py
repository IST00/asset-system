"""add supplier and asset data foundation

Revision ID: 006
Revises: 005
Create Date: 2026-07-23
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


_PERMISSIONS = (
    (
        "supplier:view",
        "查看供应商",
        "supplier",
        ("SUPER_ADMIN", "ASSET_ADMIN", "USER"),
    ),
    (
        "supplier:create",
        "新增供应商",
        "supplier",
        ("SUPER_ADMIN", "ASSET_ADMIN"),
    ),
    (
        "supplier:edit",
        "编辑供应商",
        "supplier",
        ("SUPER_ADMIN", "ASSET_ADMIN"),
    ),
    (
        "supplier:disable",
        "停用恢复供应商",
        "supplier",
        ("SUPER_ADMIN", "ASSET_ADMIN"),
    ),
    ("supplier:delete", "删除供应商", "supplier", ("SUPER_ADMIN",)),
    (
        "asset:data:complete",
        "补充资产资料",
        "asset",
        ("SUPER_ADMIN", "ASSET_ADMIN"),
    ),
    (
        "asset:service-life:update",
        "调整资产使用期限",
        "asset",
        ("SUPER_ADMIN", "ASSET_ADMIN"),
    ),
)

_BACKFILL_BATCH_SIZE = 500


def _supplier_code_sequences_table() -> sa.TableClause:
    return sa.table(
        "supplier_code_sequences",
        sa.column("prefix", sa.String(length=16)),
        sa.column("current_value", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _create_supplier_tables() -> None:
    op.create_table(
        "supplier_code_sequences",
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("prefix"),
    )
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unified_social_credit_code", sa.String(length=64), nullable=True),
        sa.Column("contact_name", sa.String(length=128), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("remark", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suppliers_code", "suppliers", ["code"], unique=True)
    op.create_index("ix_suppliers_name", "suppliers", ["name"], unique=True)
    op.create_index(
        "ix_suppliers_unified_social_credit_code",
        "suppliers",
        ["unified_social_credit_code"],
        unique=True,
    )
    op.create_index("ix_suppliers_status", "suppliers", ["status"], unique=False)

    sequence_table = _supplier_code_sequences_table()
    now = datetime.now(tz=timezone.utc)
    prefix = sa.bindparam("prefix", value="SUP", type_=sa.String(length=16))
    sequence_values = sa.select(
        prefix,
        sa.bindparam("current_value", value=0, type_=sa.Integer()),
        sa.bindparam("created_at", value=now, type_=sa.DateTime(timezone=True)),
        sa.bindparam("updated_at", value=now, type_=sa.DateTime(timezone=True)),
    ).where(
        ~sa.exists(
            sa.select(sa.literal(1))
            .select_from(sequence_table)
            .where(sequence_table.c.prefix == prefix)
        )
    )
    op.get_bind().execute(
        sa.insert(sequence_table).from_select(
            ["prefix", "current_value", "created_at", "updated_at"],
            sequence_values,
        )
    )


def _add_nullable_asset_columns() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("service_life_months", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("expected_expiry_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("custom_attributes", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "data_completeness",
                sa.String(length=16),
                nullable=True,
            )
        )
        batch_op.create_index("ix_assets_supplier_id", ["supplier_id"], unique=False)
        batch_op.create_index(
            "ix_assets_data_completeness",
            ["data_completeness"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_assets_supplier_id",
            "suppliers",
            ["supplier_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def _add_nullable_stock_in_columns() -> None:
    with op.batch_alter_table("stock_in_items") as batch_op:
        batch_op.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("supplier_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("service_life_months", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("expected_expiry_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("custom_attributes", sa.JSON(), nullable=True))
        batch_op.create_index(
            "ix_stock_in_items_supplier_id", ["supplier_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_stock_in_items_supplier_id",
            "suppliers",
            ["supplier_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def _calculate_expected_expiry(purchase_date: date, service_life_months: int) -> date:
    month_index = (
        purchase_date.year * 12 + purchase_date.month - 1 + service_life_months
    )
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(purchase_date.day, monthrange(year, month)[1]))


def _backfill_existing_rows() -> None:
    bind = op.get_bind()
    categories = sa.table(
        "asset_categories",
        sa.column("id", sa.Integer()),
        sa.column("service_life_months", sa.Integer()),
    )
    assets = sa.table(
        "assets",
        sa.column("id", sa.Integer()),
        sa.column("category_id", sa.Integer()),
        sa.column("purchase_date", sa.Date()),
        sa.column("service_life_months", sa.Integer()),
        sa.column("expected_expiry_date", sa.Date()),
        sa.column("custom_attributes", sa.JSON()),
        sa.column("data_completeness", sa.String(length=16)),
    )
    stock_in_items = sa.table(
        "stock_in_items",
        sa.column("id", sa.Integer()),
        sa.column("category_id", sa.Integer()),
        sa.column("purchase_date", sa.Date()),
        sa.column("service_life_months", sa.Integer()),
        sa.column("expected_expiry_date", sa.Date()),
        sa.column("custom_attributes", sa.JSON()),
    )

    asset_update = (
        sa.update(assets)
        .where(assets.c.id == sa.bindparam("asset_row_id", type_=assets.c.id.type))
        .values(
            service_life_months=sa.bindparam(
                "asset_service_life_months",
                type_=assets.c.service_life_months.type,
            ),
            expected_expiry_date=sa.bindparam(
                "asset_expected_expiry_date",
                type_=assets.c.expected_expiry_date.type,
            ),
            custom_attributes=sa.bindparam(
                "asset_custom_attributes", type_=assets.c.custom_attributes.type
            ),
            data_completeness=sa.bindparam(
                "asset_data_completeness", type_=assets.c.data_completeness.type
            ),
        )
    )
    last_asset_id: int | None = None
    while True:
        asset_page = (
            sa.select(
                assets.c.id,
                assets.c.purchase_date,
                categories.c.service_life_months,
            )
            .join(categories, categories.c.id == assets.c.category_id)
            .order_by(assets.c.id)
            .limit(_BACKFILL_BATCH_SIZE)
        )
        if last_asset_id is not None:
            asset_page = asset_page.where(assets.c.id > last_asset_id)
        with bind.execute(asset_page).mappings() as result:
            asset_rows = list(result)
        if not asset_rows:
            break
        bind.execute(
            asset_update,
            [
                {
                    "asset_row_id": row["id"],
                    "asset_service_life_months": row["service_life_months"],
                    "asset_expected_expiry_date": _calculate_expected_expiry(
                        row["purchase_date"], row["service_life_months"]
                    ),
                    "asset_custom_attributes": {},
                    "asset_data_completeness": "COMPLETE",
                }
                for row in asset_rows
            ],
        )
        last_asset_id = int(asset_rows[-1]["id"])

    stock_in_update = (
        sa.update(stock_in_items)
        .where(
            stock_in_items.c.id
            == sa.bindparam("stock_in_row_id", type_=stock_in_items.c.id.type)
        )
        .values(
            service_life_months=sa.bindparam(
                "stock_in_service_life_months",
                type_=stock_in_items.c.service_life_months.type,
            ),
            expected_expiry_date=sa.bindparam(
                "stock_in_expected_expiry_date",
                type_=stock_in_items.c.expected_expiry_date.type,
            ),
            custom_attributes=sa.bindparam(
                "stock_in_custom_attributes",
                type_=stock_in_items.c.custom_attributes.type,
            ),
        )
    )
    last_stock_in_id: int | None = None
    while True:
        stock_in_page = (
            sa.select(
                stock_in_items.c.id,
                stock_in_items.c.purchase_date,
                categories.c.service_life_months,
            )
            .join(categories, categories.c.id == stock_in_items.c.category_id)
            .order_by(stock_in_items.c.id)
            .limit(_BACKFILL_BATCH_SIZE)
        )
        if last_stock_in_id is not None:
            stock_in_page = stock_in_page.where(stock_in_items.c.id > last_stock_in_id)
        with bind.execute(stock_in_page).mappings() as result:
            stock_in_rows = list(result)
        if not stock_in_rows:
            break
        bind.execute(
            stock_in_update,
            [
                {
                    "stock_in_row_id": row["id"],
                    "stock_in_service_life_months": row["service_life_months"],
                    "stock_in_expected_expiry_date": _calculate_expected_expiry(
                        row["purchase_date"], row["service_life_months"]
                    ),
                    "stock_in_custom_attributes": {},
                }
                for row in stock_in_rows
            ],
        )
        last_stock_in_id = int(stock_in_rows[-1]["id"])


def _enforce_final_nullability() -> None:
    with op.batch_alter_table("assets") as batch_op:
        for column_name in ("unit_id", "source_id", "location_id"):
            batch_op.alter_column(
                column_name,
                existing_type=sa.Integer(),
                existing_nullable=False,
                nullable=True,
            )
        batch_op.alter_column(
            "service_life_months",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "expected_expiry_date",
            existing_type=sa.Date(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "custom_attributes",
            existing_type=sa.JSON(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "data_completeness",
            existing_type=sa.String(length=16),
            existing_nullable=True,
            nullable=False,
        )
    with op.batch_alter_table("stock_in_items") as batch_op:
        batch_op.alter_column(
            "service_life_months",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "expected_expiry_date",
            existing_type=sa.Date(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "custom_attributes",
            existing_type=sa.JSON(),
            existing_nullable=True,
            nullable=False,
        )


def _seed_permissions() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    for code, name, module, role_codes in _PERMISSIONS:
        permission_id = bind.scalar(
            sa.text("SELECT id FROM permissions WHERE code = :code"),
            {"code": code},
        )
        if permission_id is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions "
                    "(code, name, module, enabled, created_at, updated_at) "
                    "VALUES (:code, :name, :module, 1, :now, :now)"
                ),
                {"code": code, "name": name, "module": module, "now": now},
            )
            permission_id = bind.scalar(
                sa.text("SELECT id FROM permissions WHERE code = :code"),
                {"code": code},
            )

        for role_code in role_codes:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, :permission_id FROM roles r "
                    "WHERE r.code = :role_code AND NOT EXISTS ("
                    "SELECT 1 FROM role_permissions rp "
                    "WHERE rp.role_id = r.id AND rp.permission_id = :permission_id)"
                ),
                {"permission_id": permission_id, "role_code": role_code},
            )


def upgrade() -> None:
    _create_supplier_tables()
    _add_nullable_asset_columns()
    _add_nullable_stock_in_columns()
    _backfill_existing_rows()
    _enforce_final_nullability()
    _seed_permissions()


def _preflight_downgrade() -> None:
    assets = sa.table(
        "assets",
        sa.column("unit_id", sa.Integer()),
        sa.column("source_id", sa.Integer()),
        sa.column("location_id", sa.Integer()),
    )
    incomplete_count = op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(assets)
        .where(
            sa.or_(
                assets.c.unit_id.is_(None),
                assets.c.source_id.is_(None),
                assets.c.location_id.is_(None),
            )
        )
    )
    if incomplete_count:
        raise RuntimeError(
            "Cannot downgrade asset data foundation while assets contain NULL "
            "unit_id/source_id/location_id values"
        )


def _delete_permissions() -> None:
    bind = op.get_bind()
    permission_codes = tuple(code for code, _name, _module, _roles in _PERMISSIONS)
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN ("
            "SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": permission_codes},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": permission_codes},
    )


def _drop_stock_in_columns() -> None:
    with op.batch_alter_table("stock_in_items") as batch_op:
        batch_op.drop_constraint("fk_stock_in_items_supplier_id", type_="foreignkey")
        batch_op.drop_index("ix_stock_in_items_supplier_id")
        batch_op.drop_column("supplier_id")
        batch_op.drop_column("supplier_snapshot")
        batch_op.drop_column("service_life_months")
        batch_op.drop_column("expected_expiry_date")
        batch_op.drop_column("custom_attributes")


def _drop_asset_columns() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("fk_assets_supplier_id", type_="foreignkey")
        batch_op.drop_index("ix_assets_supplier_id")
        batch_op.drop_index("ix_assets_data_completeness")
        batch_op.drop_column("supplier_id")
        batch_op.drop_column("service_life_months")
        batch_op.drop_column("expected_expiry_date")
        batch_op.drop_column("custom_attributes")
        batch_op.drop_column("data_completeness")
        for column_name in ("unit_id", "source_id", "location_id"):
            batch_op.alter_column(
                column_name,
                existing_type=sa.Integer(),
                existing_nullable=True,
                nullable=False,
            )


def downgrade() -> None:
    _preflight_downgrade()
    _drop_stock_in_columns()
    _drop_asset_columns()
    op.drop_table("suppliers")
    op.drop_table("supplier_code_sequences")
    _delete_permissions()
