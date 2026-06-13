"""add login and logout time to activity logs

Revision ID: 20260613_0002
Revises: 20260613_0001
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0002"
down_revision: str | None = "20260613_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activity_logs", sa.Column("login_time", sa.String(length=12), nullable=True))
    op.add_column("activity_logs", sa.Column("logout_time", sa.String(length=12), nullable=True))
    op.create_index("ix_activity_logs_login_time", "activity_logs", ["login_time"], unique=False)
    op.create_index("ix_activity_logs_logout_time", "activity_logs", ["logout_time"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_activity_logs_logout_time", table_name="activity_logs")
    op.drop_index("ix_activity_logs_login_time", table_name="activity_logs")
    op.drop_column("activity_logs", "logout_time")
    op.drop_column("activity_logs", "login_time")
