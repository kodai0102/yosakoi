from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.dept_user import DeptUser
from app.services.passwords import verify_password


settings = get_settings()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_user_available(user: DeptUser, at: datetime | None = None) -> bool:
    current = at or now_utc()
    valid_from = normalize_datetime(user.valid_from)
    valid_to = normalize_datetime(user.valid_to)
    return user.is_active and valid_from <= current <= valid_to


async def get_user_by_login_id(db: AsyncSession, login_id: str) -> DeptUser | None:
    result = await db.execute(select(DeptUser).where(DeptUser.user_id == login_id))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> DeptUser | None:
    result = await db.execute(select(DeptUser).where(DeptUser.user_no == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, login_id: str, password: str
) -> DeptUser | None:
    user = await get_user_by_login_id(db, login_id)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not is_user_available(user):
        return None
    return user


def create_access_token(user: DeptUser) -> str:
    expire = now_utc() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user.id), "role": user.role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, object] | None:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        return None
