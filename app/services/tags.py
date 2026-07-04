from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.models.tag import DancerTag, PhotoDancerTag
from app.services.photos import serialize_photo


def parse_tag_names(value: str) -> list[str]:
    normalized = value.replace("、", ",").replace("\n", ",")
    names = []
    seen = set()
    for raw_name in normalized.split(","):
        name = raw_name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name[:100])
    return names


async def list_tags_with_counts(db: AsyncSession, q: str | None = None) -> list[dict[str, object]]:
    query = (
        select(DancerTag, func.count(PhotoDancerTag.id).label("photo_count"))
        .join(PhotoDancerTag, DancerTag.id == PhotoDancerTag.dancer_tag_id)
        .join(Photo, Photo.id == PhotoDancerTag.photo_id)
        .where(Photo.is_deleted.is_(False))
        .group_by(DancerTag.id)
        .order_by(DancerTag.name.asc())
    )
    if q:
        query = query.where(DancerTag.name.ilike(f"%{q}%"))
    result = await db.execute(query)
    return [
        {
            "id": tag.id,
            "name": tag.name,
            "photo_count": photo_count,
            "created_at": tag.created_at,
        }
        for tag, photo_count in result.all()
    ]


async def get_or_create_tag(db: AsyncSession, name: str) -> DancerTag:
    result = await db.execute(select(DancerTag).where(DancerTag.name == name))
    tag = result.scalar_one_or_none()
    if tag is not None:
        return tag
    tag = DancerTag(name=name)
    db.add(tag)
    await db.flush()
    return tag


async def set_photo_tags(db: AsyncSession, photo_id: UUID, tag_names: list[str]) -> None:
    await db.execute(delete(PhotoDancerTag).where(PhotoDancerTag.photo_id == photo_id))
    for name in tag_names:
        tag = await get_or_create_tag(db, name)
        db.add(PhotoDancerTag(photo_id=photo_id, dancer_tag_id=tag.id))
    await db.commit()


async def add_tags_to_photos(db: AsyncSession, photo_ids: list[UUID], tag_names: list[str]) -> None:
    if not photo_ids or not tag_names:
        return

    for photo_id in photo_ids:
        existing_names = set(await get_photo_tag_names(db, photo_id))
        for name in tag_names:
            if name in existing_names:
                continue
            tag = await get_or_create_tag(db, name)
            db.add(PhotoDancerTag(photo_id=photo_id, dancer_tag_id=tag.id))
            existing_names.add(name)
    await db.commit()


async def get_photo_tag_names(db: AsyncSession, photo_id: UUID) -> list[str]:
    result = await db.execute(
        select(DancerTag.name)
        .join(PhotoDancerTag, DancerTag.id == PhotoDancerTag.dancer_tag_id)
        .where(PhotoDancerTag.photo_id == photo_id)
        .order_by(DancerTag.name.asc())
    )
    return list(result.scalars().all())


async def get_photo_tags_map(db: AsyncSession, photo_ids: list[UUID]) -> dict[UUID, list[str]]:
    if not photo_ids:
        return {}
    result = await db.execute(
        select(PhotoDancerTag.photo_id, DancerTag.name)
        .join(DancerTag, DancerTag.id == PhotoDancerTag.dancer_tag_id)
        .where(PhotoDancerTag.photo_id.in_(photo_ids))
        .order_by(DancerTag.name.asc())
    )
    tags: dict[UUID, list[str]] = {}
    for photo_id, tag_name in result.all():
        tags.setdefault(photo_id, []).append(tag_name)
    return tags


async def list_photos_by_tag(db: AsyncSession, tag_id: int | None = None) -> list[dict[str, object]]:
    query = (
        select(Photo)
        .join(PhotoDancerTag, Photo.id == PhotoDancerTag.photo_id)
        .where(Photo.is_deleted.is_(False))
        .order_by(Photo.taken_at.desc(), Photo.created_at.desc())
    )
    if tag_id is not None:
        query = query.where(PhotoDancerTag.dancer_tag_id == tag_id)
    result = await db.execute(query)
    photos = list(result.scalars().unique().all())
    tag_map = await get_photo_tags_map(db, [photo.id for photo in photos])
    rows = []
    for photo in photos:
        item = serialize_photo(photo)
        item["tags"] = tag_map.get(photo.id, [])
        rows.append(item)
    return rows
