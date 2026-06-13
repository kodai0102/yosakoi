import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.services.auth import now_utc
from app.services.passwords import hash_password


async def create_initial_admin() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.login_id == settings.initial_admin_login_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            print("Initial admin already exists.")
            return

        current = now_utc()
        admin = User(
            login_id=settings.initial_admin_login_id,
            display_name=settings.initial_admin_display_name,
            password_hash=hash_password(settings.initial_admin_password),
            role="admin",
            is_active=True,
            valid_from=current - timedelta(minutes=1),
            valid_to=current + timedelta(days=3650),
        )
        db.add(admin)
        await db.flush()
        db.add(
            ActivityLog(
                user_id=admin.id,
                user_name=admin.display_name,
                action_type="user_create",
                target_type="user",
                target_id=str(admin.id),
            )
        )
        await db.commit()
        print(f"Initial admin created: {admin.login_id}")


if __name__ == "__main__":
    asyncio.run(create_initial_admin())
