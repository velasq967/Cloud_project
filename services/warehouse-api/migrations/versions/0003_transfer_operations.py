"""Pasos de transferencias aplicados en la bodega (fase 6).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transfer_operations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("transfer_id", sa.String(length=50), nullable=False),
        sa.Column("step", sa.String(length=20), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("transfer_id", "step", name="uq_transfer_operation_step"),
    )
    op.create_index(
        "ix_transfer_operations_transfer_id",
        "transfer_operations",
        ["transfer_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transfer_operations_transfer_id", table_name="transfer_operations")
    op.drop_table("transfer_operations")
