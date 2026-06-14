from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.album import Album
from app.models.photo import Photo

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
THUMBNAIL_SIZE = (640, 640)
JST = ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    return datetime.now(JST)


def storage_root() -> Path:
    return Path(get_settings().local_storage_root)


def media_path(object_key: str) -> Path:
    return storage_root() / object_key


def display_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=JST)
    return value.astimezone(JST).strftime("%Y/%m/%d %H:%M")


def serialize_photo(photo: Photo) -> dict[str, object]:
    return {
        "id": str(photo.id),
        "album_id": photo.album_id,
        "original_path": photo.original_path,
        "thumbnail_path": photo.thumbnail_path,
        "file_name": photo.file_name,
        "content_type": photo.content_type,
        "file_size": photo.file_size,
        "taken_at": photo.taken_at,
        "taken_at_label": display_datetime(photo.taken_at),
        "is_deleted": photo.is_deleted,
        "deleted_at": photo.deleted_at,
        "created_at": photo.created_at,
        "updated_at": photo.updated_at,
        "media_url": f"/media/{photo.original_path}",
        "thumbnail_url": f"/media/{photo.thumbnail_path}",
        "title": photo.file_name,
    }


def validate_upload(file: UploadFile, payload: bytes) -> str:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JPG、PNG、WEBPのみアップロードできます",
        )
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="空のファイルです")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="1ファイルの上限は30MBです",
        )
    return ALLOWED_CONTENT_TYPES[file.content_type]


def open_image(payload: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(payload))
        image.verify()
        return Image.open(BytesIO(payload))
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="画像ファイルとして読み込めません",
        ) from exc


def extract_taken_at(image: Image.Image) -> datetime:
    try:
        exif = image.getexif()
        raw_value = exif.get(36867) or exif.get(306)
    except (AttributeError, OSError):
        raw_value = None
    if raw_value:
        try:
            return datetime.strptime(str(raw_value), "%Y:%m:%d %H:%M:%S").replace(tzinfo=JST)
        except ValueError:
            pass
    return now_jst()


def object_keys(album_id: int, photo_id: UUID, extension: str) -> tuple[str, str]:
    prefix = f"photos/{album_id}/{photo_id}"
    return f"{prefix}/original{extension}", f"{prefix}/thumbnail.webp"


def save_bytes(object_key: str, payload: bytes) -> None:
    path = media_path(object_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def make_thumbnail(image: Image.Image) -> bytes:
    image = image.convert("RGB")
    image.thumbnail(THUMBNAIL_SIZE)
    output = BytesIO()
    image.save(output, format="WEBP", quality=82)
    return output.getvalue()


async def list_album_photos(db: AsyncSession, album_id: int) -> list[Photo]:
    result = await db.execute(
        select(Photo)
        .where(Photo.album_id == album_id, Photo.is_deleted.is_(False))
        .order_by(Photo.taken_at.asc(), Photo.created_at.asc())
    )
    return list(result.scalars().all())


async def get_photo_or_404(db: AsyncSession, photo_id: UUID) -> Photo:
    photo = await db.get(Photo, photo_id)
    if photo is None or photo.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="写真が存在しません")
    return photo


async def create_photo(db: AsyncSession, album: Album, file: UploadFile) -> Photo:
    payload = await file.read()
    extension = validate_upload(file, payload)
    image = open_image(payload)
    photo_id = uuid4()
    original_key, thumbnail_key = object_keys(album.id, photo_id, extension)
    save_bytes(original_key, payload)
    save_bytes(thumbnail_key, make_thumbnail(image))

    photo = Photo(
        id=photo_id,
        album_id=album.id,
        original_path=original_key,
        thumbnail_path=thumbnail_key,
        file_name=(file.filename or f"{photo_id}{extension}")[:255],
        content_type=file.content_type or "application/octet-stream",
        file_size=len(payload),
        taken_at=extract_taken_at(image),
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


async def logical_delete_photo(db: AsyncSession, photo_id: UUID) -> Photo:
    photo = await get_photo_or_404(db, photo_id)
    photo.is_deleted = True
    photo.deleted_at = now_jst()
    await db.commit()
    await db.refresh(photo)
    return photo
