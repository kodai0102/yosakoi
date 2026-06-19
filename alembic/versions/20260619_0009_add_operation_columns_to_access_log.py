"""add operation columns to access log

Revision ID: 20260619_0009
Revises: 20260617_0008
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260619_0009"
down_revision: Union[str, None] = "20260617_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("access_log", sa.Column("operation_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("access_log", sa.Column("operation_name", sa.String(length=100), nullable=True))
    op.add_column("access_log", sa.Column("operation_target", sa.Text(), nullable=True))
    op.create_index(op.f("ix_access_log_operation_time"), "access_log", ["operation_time"], unique=False)
    op.create_index(op.f("ix_access_log_operation_name"), "access_log", ["operation_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_access_log_operation_name"), table_name="access_log")
    op.drop_index(op.f("ix_access_log_operation_time"), table_name="access_log")
    op.drop_column("access_log", "operation_target")
    op.drop_column("access_log", "operation_name")
    op.drop_column("access_log", "operation_time")
