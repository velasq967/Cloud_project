"""Auditoría y trabajos de reporte.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("consumer", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("warehouse_id", sa.String(length=50), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("event_id", "consumer", name="uq_audit_event_consumer"),
    )
    op.create_index("ix_audit_log_event_id", "audit_log", ["event_id"], unique=False)
    op.create_index(
        "ix_audit_log_warehouse_id", "audit_log", ["warehouse_id"], unique=False
    )
    op.create_index(
        "ix_audit_log_correlation_id", "audit_log", ["correlation_id"], unique=False
    )

    op.create_table(
        "report_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_report_jobs_status", "report_jobs", ["status"], unique=False)
    op.create_index(
        "ix_report_jobs_correlation_id", "report_jobs", ["correlation_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_report_jobs_correlation_id", table_name="report_jobs")
    op.drop_index("ix_report_jobs_status", table_name="report_jobs")
    op.drop_table("report_jobs")
    op.drop_index("ix_audit_log_correlation_id", table_name="audit_log")
    op.drop_index("ix_audit_log_warehouse_id", table_name="audit_log")
    op.drop_index("ix_audit_log_event_id", table_name="audit_log")
    op.drop_table("audit_log")
