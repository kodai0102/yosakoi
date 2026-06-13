import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.dept_user import DeptUser
from app.services.auth import now_utc
from app.services.passwords import hash_password


async def create_initial_admin() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DeptUser).where(DeptUser.user_id == settings.initial_admin_login_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            print("Initial admin already exists.")
            return

        current = now_utc()
        admin = DeptUser(
            user_id=settings.initial_admin_login_id,
            user_name=settings.initial_admin_display_name,
            password=hash_password(settings.initial_admin_password),
            role="admin",
            is_active=True,
            start_date=current - timedelta(minutes=1),
            end_date=current + timedelta(days=3650),
        )
        db.add(admin)
        await db.commit()
        print(f"Initial admin created: {admin.user_id}")


if __name__ == "__main__":
    asyncio.run(create_initial_admin())
