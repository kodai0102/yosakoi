"""create albums

Revision ID: 20260614_0005
Revises: 20260613_0004
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260614_0005"
down_revision: str | None = "20260613_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "albums",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("publish_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publish_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("publish_from <= publish_to", name="ck_albums_publish_period"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_albums_year", "albums", ["year"], unique=False)
    op.create_index("ix_albums_event_name", "albums", ["event_name"], unique=False)
    op.create_index("ix_albums_publish_from", "albums", ["publish_from"], unique=False)
    op.create_index("ix_albums_publish_to", "albums", ["publish_to"], unique=False)
    op.create_index(
        "ix_albums_year_event_name",
        "albums",
        ["year", "event_name"],
        unique=False,
    )
    op.create_index(
        "ix_albums_publish_period",
        "albums",
        ["publish_from", "publish_to"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_albums_publish_period", table_name="albums")
    op.drop_index("ix_albums_year_event_name", table_name="albums")
    op.drop_index("ix_albums_publish_to", table_name="albums")
    op.drop_index("ix_albums_publish_from", table_name="albums")
    op.drop_index("ix_albums_event_name", table_name="albums")
    op.drop_index("ix_albums_year", table_name="albums")
    op.drop_table("albums")
