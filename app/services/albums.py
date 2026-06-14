from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.models.album import Album


APP_TIMEZONE = ZoneInfo("Asia/Tokyo")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=APP_TIMEZONE)
    return value


def display_datetime(value: datetime) -> datetime:
    return normalize_datetime(value).astimezone(APP_TIMEZONE)


def is_album_published(album: Album, at: datetime | None = None) -> bool:
    current = at or now_utc()
    publish_from = normalize_datetime(album.publish_from)
    publish_to = normalize_datetime(album.publish_to)
    return publish_from <= current <= publish_to


def album_period(album: Album) -> str:
    return (
        f"{display_datetime(album.publish_from).strftime('%Y/%m/%d')} - "
        f"{display_datetime(album.publish_to).strftime('%Y/%m/%d')}"
    )


def album_status(album: Album) -> str:
    return "公開中" if is_album_published(album) else "非公開"


def serialize_album(album: Album) -> dict[str, object]:
    return {
        "id": album.id,
        "year": album.year,
        "event_name": album.event_name,
        "event_date": album.event_date,
        "title": album.title,
        "description": album.description,
        "thumbnail_path": album.thumbnail_path,
        "publish_from": album.publish_from,
        "publish_to": album.publish_to,
        "created_at": album.created_at,
        "updated_at": album.updated_at,
        "period": album_period(album),
        "status": album_status(album),
        "count": 0,
        "tags": [str(album.year), album.event_name],
    }
