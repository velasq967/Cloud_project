"""Outbox y eventos procesados (fase 10).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("routing_key", sa.String(length=200), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_outbox_event_id"),
    )
    op.create_index("ix_outbox_events_event_id", "outbox_events", ["event_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_correlation_id", "outbox_events", ["correlation_id"])
    op.create_index("ix_outbox_events_published_at", "outbox_events", ["published_at"])

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("consumer", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_events_published_at", table_name="outbox_events")
    op.drop_index("ix_outbox_events_correlation_id", table_name="outbox_events")
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_index("ix_outbox_events_event_id", table_name="outbox_events")
    op.drop_table("outbox_events")
