"""create photos

Revision ID: 20260614_0006
Revises: 20260614_0005
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260614_0006"
down_revision: Union[str, None] = "20260614_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("access_log", sa.Column("pic_upload_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("access_log", sa.Column("pic_upload_list", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_access_log_pic_upload_time"),
        "access_log",
        ["pic_upload_time"],
        unique=False,
    )
    op.create_table(
        "photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("album_id", sa.BigInteger(), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("thumbnail_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_photos_album_id"), "photos", ["album_id"], unique=False)
    op.create_index(op.f("ix_photos_created_at"), "photos", ["created_at"], unique=False)
    op.create_index(op.f("ix_photos_is_deleted"), "photos", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_photos_taken_at"), "photos", ["taken_at"], unique=False)
    op.create_index(
        "ix_photos_album_deleted_taken",
        "photos",
        ["album_id", "is_deleted", "taken_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_photos_album_deleted_taken", table_name="photos")
    op.drop_index(op.f("ix_photos_taken_at"), table_name="photos")
    op.drop_index(op.f("ix_photos_is_deleted"), table_name="photos")
    op.drop_index(op.f("ix_photos_created_at"), table_name="photos")
    op.drop_index(op.f("ix_photos_album_id"), table_name="photos")
    op.drop_table("photos")
    op.drop_index(op.f("ix_access_log_pic_upload_time"), table_name="access_log")
    op.drop_column("access_log", "pic_upload_list")
    op.drop_column("access_log", "pic_upload_time")
