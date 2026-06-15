"""create tags

Revision ID: 20260615_0007
Revises: 20260614_0006
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260615_0007"
down_revision: Union[str, None] = "20260614_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dancer_tags",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_dancer_tags_name"), "dancer_tags", ["name"], unique=True)
    op.create_table(
        "photo_dancer_tags",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dancer_tag_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dancer_tag_id"], ["dancer_tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("photo_id", "dancer_tag_id", name="uq_photo_dancer_tags_photo_tag"),
    )
    op.create_index(op.f("ix_photo_dancer_tags_dancer_tag_id"), "photo_dancer_tags", ["dancer_tag_id"], unique=False)
    op.create_index(op.f("ix_photo_dancer_tags_photo_id"), "photo_dancer_tags", ["photo_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_photo_dancer_tags_photo_id"), table_name="photo_dancer_tags")
    op.drop_index(op.f("ix_photo_dancer_tags_dancer_tag_id"), table_name="photo_dancer_tags")
    op.drop_table("photo_dancer_tags")
    op.drop_index(op.f("ix_dancer_tags_name"), table_name="dancer_tags")
    op.drop_table("dancer_tags")
