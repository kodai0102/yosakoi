from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_log import AccessLog
from app.models.dept_user import DeptUser


def current_activity_time() -> datetime:
    return datetime.now(ZoneInfo("Asia/Tokyo"))


async def record_activity(
    db: AsyncSession,
    request: Request | None,
    action_type: str,
    user: DeptUser | None = None,
    user_name: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    activity_time = current_activity_time()
    if action_type == "login_success":
        db.add(
            AccessLog(
                user_name=user.display_name if user else user_name,
                user_id=user.login_id if user else target_id,
                logon_time=activity_time,
            )
        )
        await db.commit()
        return

    if action_type == "logout" and user is not None:
        result = await db.execute(
            select(AccessLog)
            .where(AccessLog.user_id == user.login_id, AccessLog.logoff_time.is_(None))
            .order_by(AccessLog.rireki_no.desc())
            .limit(1)
        )
        log = result.scalar_one_or_none()
        if log is None:
            log = AccessLog(user_name=user.display_name, user_id=user.login_id)
            db.add(log)
        log.logoff_time = activity_time
        await db.commit()
        return

    if action_type == "photo_download":
        db.add(
            AccessLog(
                user_name=user.display_name if user else user_name,
                user_id=user.login_id if user else None,
                pic_download_time=activity_time,
                pic_download_list=target_id,
            )
        )
        await db.commit()
        return

    if action_type == "photo_upload":
        db.add(
            AccessLog(
                user_name=user.display_name if user else user_name,
                user_id=user.login_id if user else None,
                pic_upload_time=activity_time,
                pic_upload_list=target_id,
            )
        )
        await db.commit()
        return

    if action_type == "favorite":
        db.add(
            AccessLog(
                user_name=user.display_name if user else user_name,
                user_id=user.login_id if user else None,
                operation_time=activity_time,
                favorite=target_id,
            )
        )
        await db.commit()
        return

    if action_type == "favorite_remove":
        db.add(
            AccessLog(
                user_name=user.display_name if user else user_name,
                user_id=user.login_id if user else None,
                operation_time=activity_time,
                favorite=f"unfavorite:{target_id}",
            )
        )
        await db.commit()
        return

    db.add(
        AccessLog(
            user_name=user.display_name if user else user_name,
            user_id=user.login_id if user else None,
            operation_time=activity_time,
            operation_name=action_type,
            operation_target=target_id,
        )
    )
    await db.commit()
