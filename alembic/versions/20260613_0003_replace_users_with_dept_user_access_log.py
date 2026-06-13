"""replace users with dept user and access log

Revision ID: 20260613_0003
Revises: 20260613_0002
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_0003"
down_revision: str | None = "20260613_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dept_user",
        sa.Column("user_no", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("user_name", sa.String(length=100), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("create_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_dept_user_role"),
        sa.CheckConstraint("start_date <= end_date", name="ck_dept_user_period"),
        sa.PrimaryKeyConstraint("user_no", "user_id"),
        sa.UniqueConstraint("user_id", name="uq_dept_user_user_id"),
    )
    op.create_index("ix_dept_user_user_id", "dept_user", ["user_id"], unique=False)
    op.create_index("ix_dept_user_role", "dept_user", ["role"], unique=False)
    op.create_index("ix_dept_user_is_active", "dept_user", ["is_active"], unique=False)

    op.execute(
        """
        INSERT INTO dept_user (
            user_no, user_id, user_name, password, role, is_active, create_date, start_date, end_date
        )
        SELECT id, login_id, display_name, password_hash, role, is_active, created_at, valid_from, valid_to
        FROM users
        ON CONFLICT (user_id) DO NOTHING
        """
    )
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('dept_user', 'user_no'),
            COALESCE((SELECT MAX(user_no) FROM dept_user), 0) + 1,
            false
        )
        """
    )

    op.create_table(
        "access_log",
        sa.Column("rireki_no", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_name", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("logon_time", sa.String(length=12), nullable=True),
        sa.Column("logoff_time", sa.String(length=12), nullable=True),
        sa.Column("pic_download_time", sa.String(length=12), nullable=True),
        sa.Column("pic_download_list", sa.Text(), nullable=True),
        sa.Column("favorite", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["dept_user.user_id"]),
        sa.PrimaryKeyConstraint("rireki_no"),
    )
    op.create_index("ix_access_log_user_id", "access_log", ["user_id"], unique=False)
    op.create_index("ix_access_log_logon_time", "access_log", ["logon_time"], unique=False)
    op.create_index("ix_access_log_logoff_time", "access_log", ["logoff_time"], unique=False)
    op.create_index("ix_access_log_pic_download_time", "access_log", ["pic_download_time"], unique=False)

    op.execute(
        """
        INSERT INTO access_log (user_name, user_id, logon_time, logoff_time)
        SELECT al.user_name, u.login_id, al.login_time, al.logout_time
        FROM activity_logs al
        LEFT JOIN users u ON u.id = al.user_id
        WHERE al.login_time IS NOT NULL OR al.logout_time IS NOT NULL
        """
    )

    op.drop_table("activity_logs")
    op.drop_table("users")


def downgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("login_id", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_users_role"),
        sa.CheckConstraint("valid_from <= valid_to", name="ck_users_valid_period"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_login_id", "users", ["login_id"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_is_active", "users", ["is_active"], unique=False)
    op.create_index("ix_users_active_period", "users", ["is_active", "valid_from", "valid_to"], unique=False)
    op.execute(
        """
        INSERT INTO users (
            id, login_id, display_name, password_hash, role, is_active, created_at, updated_at, valid_from, valid_to
        )
        SELECT user_no, user_id, user_name, password, role, is_active, create_date, create_date, start_date, end_date
        FROM dept_user
        ON CONFLICT (login_id) DO NOTHING
        """
    )

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("user_name", sa.String(length=100), nullable=True),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("login_time", sa.String(length=12), nullable=True),
        sa.Column("logout_time", sa.String(length=12), nullable=True),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_logs_user_id", "activity_logs", ["user_id"], unique=False)
    op.create_index("ix_activity_logs_action_type", "activity_logs", ["action_type"], unique=False)
    op.create_index("ix_activity_logs_created_at", "activity_logs", ["created_at"], unique=False)
    op.create_index("ix_activity_logs_login_time", "activity_logs", ["login_time"], unique=False)
    op.create_index("ix_activity_logs_logout_time", "activity_logs", ["logout_time"], unique=False)

    op.drop_index("ix_access_log_pic_download_time", table_name="access_log")
    op.drop_index("ix_access_log_logoff_time", table_name="access_log")
    op.drop_index("ix_access_log_logon_time", table_name="access_log")
    op.drop_index("ix_access_log_user_id", table_name="access_log")
    op.drop_table("access_log")
    op.drop_index("ix_dept_user_is_active", table_name="dept_user")
    op.drop_index("ix_dept_user_role", table_name="dept_user")
    op.drop_index("ix_dept_user_user_id", table_name="dept_user")
    op.drop_table("dept_user")
