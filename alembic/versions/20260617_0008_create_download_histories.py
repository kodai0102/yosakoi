"""create download histories

Revision ID: 20260617_0008
Revises: 20260615_0007
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260617_0008"
down_revision: Union[str, None] = "20260615_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "download_histories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=100), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["dept_user.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_download_histories_downloaded_at"), "download_histories", ["downloaded_at"], unique=False)
    op.create_index(op.f("ix_download_histories_photo_id"), "download_histories", ["photo_id"], unique=False)
    op.create_index(op.f("ix_download_histories_user_id"), "download_histories", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_download_histories_user_id"), table_name="download_histories")
    op.drop_index(op.f("ix_download_histories_photo_id"), table_name="download_histories")
    op.drop_index(op.f("ix_download_histories_downloaded_at"), table_name="download_histories")
    op.drop_table("download_histories")
