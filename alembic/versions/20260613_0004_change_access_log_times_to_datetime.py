"""change access log times to datetime

Revision ID: 20260613_0004
Revises: 20260613_0003
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0004"
down_revision: str | None = "20260613_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "access_log",
        "logon_time",
        existing_type=sa.String(length=12),
        type_=sa.DateTime(timezone=True),
        postgresql_using=(
            "CASE WHEN logon_time IS NULL THEN NULL "
            "ELSE to_timestamp(logon_time, 'YYYYMMDDHH24MI')::timestamp AT TIME ZONE 'Asia/Tokyo' END"
        ),
    )
    op.alter_column(
        "access_log",
        "logoff_time",
        existing_type=sa.String(length=12),
        type_=sa.DateTime(timezone=True),
        postgresql_using=(
            "CASE WHEN logoff_time IS NULL THEN NULL "
            "ELSE to_timestamp(logoff_time, 'YYYYMMDDHH24MI')::timestamp AT TIME ZONE 'Asia/Tokyo' END"
        ),
    )
    op.alter_column(
        "access_log",
        "pic_download_time",
        existing_type=sa.String(length=12),
        type_=sa.DateTime(timezone=True),
        postgresql_using=(
            "CASE WHEN pic_download_time IS NULL THEN NULL "
            "ELSE to_timestamp(pic_download_time, 'YYYYMMDDHH24MI')::timestamp AT TIME ZONE 'Asia/Tokyo' END"
        ),
    )


def downgrade() -> None:
    op.alter_column(
        "access_log",
        "pic_download_time",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(length=12),
        postgresql_using="to_char(pic_download_time AT TIME ZONE 'Asia/Tokyo', 'YYYYMMDDHH24MI')",
    )
    op.alter_column(
        "access_log",
        "logoff_time",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(length=12),
        postgresql_using="to_char(logoff_time AT TIME ZONE 'Asia/Tokyo', 'YYYYMMDDHH24MI')",
    )
    op.alter_column(
        "access_log",
        "logon_time",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(length=12),
        postgresql_using="to_char(logon_time AT TIME ZONE 'Asia/Tokyo', 'YYYYMMDDHH24MI')",
    )
