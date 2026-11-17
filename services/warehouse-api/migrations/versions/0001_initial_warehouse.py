"""Esquema inicial de una bodega.

Revision ID: 0001
Revises:
Create Date: 2026-11-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default="unit"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_products_id", "products", ["id"], unique=False)
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)

    op.create_table(
        "inventory",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("warehouse_id", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "product_id", "warehouse_id", name="uq_inventory_product_warehouse"
        ),
        sa.CheckConstraint("quantity >= 0", name="chk_inventory_quantity_non_negative"),
        sa.CheckConstraint(
            "reserved_quantity >= 0", name="chk_inventory_reserved_non_negative"
        ),
        sa.CheckConstraint(
            "reserved_quantity <= quantity", name="chk_inventory_reserved_le_quantity"
        ),
    )
    op.create_index("ix_inventory_product_id", "inventory", ["product_id"], unique=False)
    op.create_index(
        "ix_inventory_warehouse_id", "inventory", ["warehouse_id"], unique=False
    )

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("warehouse_id", sa.String(length=50), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "type IN ('RECEIPT','SHIPMENT','ADJUSTMENT','RESERVATION',"
            "'RELEASE','TRANSFER_OUT','TRANSFER_IN','RETURN')",
            name="chk_movement_type",
        ),
        sa.CheckConstraint("quantity > 0", name="chk_movement_quantity_positive"),
    )
    op.create_index(
        "ix_movements_product_id", "inventory_movements", ["product_id"], unique=False
    )
    op.create_index(
        "ix_movements_warehouse_id",
        "inventory_movements",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        "ix_movements_created_at", "inventory_movements", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_movements_created_at", table_name="inventory_movements")
    op.drop_index("ix_movements_warehouse_id", table_name="inventory_movements")
    op.drop_index("ix_movements_product_id", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index("ix_inventory_warehouse_id", table_name="inventory")
    op.drop_index("ix_inventory_product_id", table_name="inventory")
    op.drop_table("inventory")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_index("ix_products_id", table_name="products")
    op.drop_table("products")
