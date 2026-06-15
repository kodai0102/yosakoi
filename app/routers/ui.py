from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.access_log import AccessLog
from app.models.dept_user import DeptUser
from app.models.photo import Photo
from app.services.photos import display_datetime, serialize_photo
from app.services.tags import list_photos_by_tag, list_tags_with_counts

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")
UNFAVORITE_PREFIX = "unfavorite:"


def sample_albums() -> list[dict[str, object]]:
    return [
        {
            "id": 1,
            "title": "第25回 どまつり",
            "period": "2025/08/01 - 2025/08/10",
            "count": 245,
            "status": "公開中",
            "tags": ["本祭", "名古屋", "どまつり", "2025"],
        },
        {
            "id": 2,
            "title": "よさこい祭り 2025",
            "period": "2025/07/10 - 2025/07/15",
            "count": 312,
            "status": "公開中",
            "tags": ["高知", "本祭", "2025"],
        },
        {
            "id": 3,
            "title": "スーパーよさこい 2025",
            "period": "2025/06/07 - 2025/06/08",
            "count": 189,
            "status": "公開中",
            "tags": ["東京", "原宿", "2025"],
        },
        {
            "id": 4,
            "title": "春の演舞会 2025",
            "period": "2025/04/20",
            "count": 128,
            "status": "終了",
            "tags": ["演舞会", "春"],
        },
    ]


def sample_photos() -> list[dict[str, object]]:
    return [
        {"id": i, "title": f"photo-{i:03}", "taken_at": "2025/08/02 14:23"}
        for i in range(1, 13)
    ]


def parse_photo_ids(value: str | None) -> list[UUID]:
    if not value:
        return []
    ids = []
    for raw_id in value.split(","):
        try:
            ids.append(UUID(raw_id.strip()))
        except ValueError:
            continue
    return ids


def favorite_value_photo_id(value: str | None) -> tuple[UUID | None, bool]:
    if not value:
        return None, False
    is_removed = value.startswith(UNFAVORITE_PREFIX)
    raw_id = value.removeprefix(UNFAVORITE_PREFIX)
    try:
        return UUID(raw_id), is_removed
    except ValueError:
        return None, False


async def photos_by_ids(db: AsyncSession, photo_ids: list[UUID]) -> list[Photo]:
    if not photo_ids:
        return []
    result = await db.execute(
        select(Photo).where(Photo.id.in_(photo_ids), Photo.is_deleted.is_(False))
    )
    photos = {photo.id: photo for photo in result.scalars().all()}
    return [photos[photo_id] for photo_id in photo_ids if photo_id in photos]


@router.get("/albums", response_class=HTMLResponse)
async def albums_page(
    request: Request,
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "current_user": current_user, "albums": sample_albums()},
    )


@router.get("/albums/{album_id}", response_class=HTMLResponse)
async def album_photos_page(
    request: Request,
    album_id: int,
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    albums = sample_albums()
    album = next((item for item in albums if item["id"] == album_id), albums[0])
    return templates.TemplateResponse(
        "album_photos.html",
        {
            "request": request,
            "current_user": current_user,
            "album": album,
            "photos": sample_photos(),
        },
    )


@router.get("/photos/{photo_id}", response_class=HTMLResponse)
async def photo_detail_page(
    request: Request,
    photo_id: int,
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "photo_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "photo_id": photo_id,
            "album": sample_albums()[0],
        },
    )


@router.get("/favorites", response_class=HTMLResponse)
async def favorites_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    result = await db.execute(
        select(AccessLog)
        .where(AccessLog.user_id == current_user.login_id, AccessLog.favorite.is_not(None))
        .order_by(AccessLog.rireki_no.desc())
    )
    photo_ids = []
    seen = set()
    for log in result.scalars().all():
        photo_id, is_removed = favorite_value_photo_id(log.favorite)
        if photo_id is None or photo_id in seen:
            continue
        seen.add(photo_id)
        if not is_removed:
            photo_ids.append(photo_id)
    photos = [serialize_photo(photo) for photo in await photos_by_ids(db, photo_ids)]
    return templates.TemplateResponse(
        "favorites.html",
        {"request": request, "current_user": current_user, "photos": photos},
    )


@router.get("/tags", response_class=HTMLResponse)
async def tag_search_page(
    request: Request,
    tag_id: int | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    tags = await list_tags_with_counts(db, q)
    selected_tag = next((tag for tag in tags if tag["id"] == tag_id), None)
    photos = await list_photos_by_tag(db, tag_id) if tag_id is not None else []
    return templates.TemplateResponse(
        "tag_search.html",
        {
            "request": request,
            "current_user": current_user,
            "tags": tags,
            "photos": photos,
            "query": q or "",
            "selected_tag": selected_tag,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "current_user": current_user,
            "albums": sample_albums()[:3],
            "photos": sample_photos()[:6],
        },
    )


@router.get("/downloads", response_class=HTMLResponse)
async def downloads_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    result = await db.execute(
        select(AccessLog)
        .where(
            AccessLog.user_id == current_user.login_id,
            AccessLog.pic_download_time.is_not(None),
            AccessLog.pic_download_list.is_not(None),
        )
        .order_by(AccessLog.rireki_no.desc())
    )
    rows = []
    for log in result.scalars().all():
        for photo in await photos_by_ids(db, parse_photo_ids(log.pic_download_list)):
            item = serialize_photo(photo)
            item["downloaded_at_label"] = display_datetime(log.pic_download_time)
            rows.append(item)
    return templates.TemplateResponse(
        "downloads.html",
        {"request": request, "current_user": current_user, "photos": rows},
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard_page(
    request: Request,
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/dashboard.html", {"request": request, "current_user": current_user}
    )


@router.get("/admin/albums", response_class=HTMLResponse)
async def admin_albums_page(
    request: Request,
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/albums.html",
        {"request": request, "current_user": current_user, "albums": sample_albums()},
    )


@router.get("/admin/albums/{album_id}/photos", response_class=HTMLResponse)
async def admin_photos_page(
    request: Request,
    album_id: int,
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/photos.html",
        {
            "request": request,
            "current_user": current_user,
            "album": sample_albums()[0],
            "photos": sample_photos(),
        },
    )


@router.get("/admin/tags", response_class=HTMLResponse)
async def admin_tags_page(
    request: Request,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    tags = await list_tags_with_counts(db, q)
    return templates.TemplateResponse(
        "admin/tags.html",
        {
            "request": request,
            "current_user": current_user,
            "tags": tags,
            "query": q or "",
        },
    )


@router.get("/admin/logs", response_class=HTMLResponse)
async def admin_logs_page(
    request: Request,
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    logs = [
        {
            "action": "login_success",
            "user": "管理者",
            "login_time": "202606131710",
            "logout_time": "",
            "at": "2026/06/13 17:10",
        },
        {
            "action": "logout",
            "user": "管理者",
            "login_time": "",
            "logout_time": "202606131705",
            "at": "2026/06/13 17:05",
        },
        {
            "action": "user_create",
            "user": "管理者",
            "login_time": "",
            "logout_time": "",
            "at": "2026/06/13 17:00",
        },
    ]
    return templates.TemplateResponse(
        "admin/logs.html",
        {"request": request, "current_user": current_user, "logs": logs},
    )
