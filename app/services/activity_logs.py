from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.user import User


async def record_activity(
    db: AsyncSession,
    request: Request | None,
    action_type: str,
    user: User | None = None,
    user_name: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    log = ActivityLog(
        user_id=user.id if user else None,
        user_name=user.display_name if user else user_name,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(log)
    await db.commit()
