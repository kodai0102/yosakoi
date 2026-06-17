from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dept_user import DeptUser
from app.models.download_history import DownloadHistory
from app.models.photo import Photo

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
IMAGE_MIME_PREFIX = "image/"


def client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip() or None
    if request.client is None:
        return None
    return request.client.host


def image_file_type(photo: Photo) -> str:
    content_type = (photo.content_type or "").lower()
    filename = (photo.file_name or "").lower()
    extension = ""
    if "." in filename:
        extension = f".{filename.rsplit('.', maxsplit=1)[-1]}"

    if content_type.startswith(IMAGE_MIME_PREFIX):
        return content_type.removeprefix(IMAGE_MIME_PREFIX).upper()
    if extension in SUPPORTED_IMAGE_EXTENSIONS:
        return extension.removeprefix(".").upper()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="画像ファイルのみ保存できます",
    )


async def record_download_history(
    db: AsyncSession,
    request: Request,
    user: DeptUser,
    photo: Photo,
) -> DownloadHistory:
    history = DownloadHistory(
        user_id=user.login_id,
        photo_id=photo.id,
        original_filename=photo.file_name,
        file_type=image_file_type(photo),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)
    return history
