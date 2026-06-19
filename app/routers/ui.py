from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.access_log import AccessLog
from app.models.album import Album
from app.models.tag import DancerTag
from app.models.dept_user import DeptUser
from app.models.download_history import DownloadHistory
from app.models.photo import Photo
from app.services.activity_logs import record_activity
from app.services.downloads import record_download_history
from app.services.photos import display_datetime, media_path, serialize_photo, storage_root
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


async def favorite_photo_ids(db: AsyncSession, user: DeptUser) -> list[UUID]:
    result = await db.execute(
        select(AccessLog)
        .where(AccessLog.user_id == user.login_id, AccessLog.favorite.is_not(None))
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
    return photo_ids


def zip_entry_name(index: int, photo: Photo, used_names: set[str]) -> str:
    base_name = photo.file_name.strip() or f"{photo.id}"
    candidate = f"{index:03}_{base_name}"
    while candidate in used_names:
        candidate = f"{index:03}_{photo.id}_{base_name}"
    used_names.add(candidate)
    return candidate


def ensure_download_path(photo: Photo) -> Path | None:
    root = storage_root().resolve()
    path = media_path(photo.original_path).resolve()
    if root not in path.parents or not path.exists() or not path.is_file():
        return None
    return path


def operation_label(action: str) -> str:
    labels = {
        "login_success": "ログイン",
        "login_failed": "ログイン失敗",
        "logout": "ログアウト",
        "photo_download": "写真ダウンロード",
        "photo_upload": "写真アップロード",
        "favorite": "お気に入り追加",
        "favorite_remove": "お気に入り解除",
        "user_create": "ユーザー作成",
        "user_update": "ユーザー更新",
        "user_activate": "ユーザー有効化",
        "user_deactivate": "ユーザー無効化",
        "user_import": "CSV一括登録",
    }
    return labels.get(action, action)


def operation_category(action: str) -> str:
    if action.startswith("login") or action == "logout":
        return "認証"
    if action.startswith("user"):
        return "ユーザー"
    if action.startswith("photo"):
        return "写真"
    if action.startswith("favorite"):
        return "お気に入り"
    return "操作"


def log_event(
    log: AccessLog,
    action: str,
    at: datetime | None,
    target: str | None = None,
) -> dict[str, object] | None:
    if at is None:
        return None
    return {
        "id": log.rireki_no,
        "action": action,
        "action_label": operation_label(action),
        "category": operation_category(action),
        "user": log.user_name or log.user_id or "-",
        "at": display_datetime(at),
        "at_value": at,
        "login_time": display_datetime(log.logon_time) if action == "login_success" else "",
        "logout_time": display_datetime(log.logoff_time) if action == "logout" else "",
        "target": target or "-",
    }


def access_log_events(logs: list[AccessLog]) -> list[dict[str, object]]:
    events = []
    for log in logs:
        candidates = [
            log_event(log, "login_success", log.logon_time),
            log_event(log, "logout", log.logoff_time),
            log_event(log, "photo_download", log.pic_download_time, log.pic_download_list),
            log_event(log, "photo_upload", log.pic_upload_time, log.pic_upload_list),
            log_event(
                log,
                "favorite_remove" if (log.favorite or "").startswith(UNFAVORITE_PREFIX) else "favorite",
                None if log.favorite is None else log.operation_time or log.logon_time or log.pic_download_time or log.pic_upload_time,
                log.favorite,
            ),
            log_event(log, log.operation_name or "", log.operation_time, log.operation_target)
            if log.operation_name
            else None,
        ]
        events.extend(event for event in candidates if event is not None)
    return sorted(events, key=lambda event: event["at_value"], reverse=True)


async def scalar_count(db: AsyncSession, query) -> int:
    result = await db.execute(query)
    return int(result.scalar_one() or 0)


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
    photo_ids = await favorite_photo_ids(db, current_user)
    photos = [serialize_photo(photo) for photo in await photos_by_ids(db, photo_ids)]
    return templates.TemplateResponse(
        "favorites.html",
        {"request": request, "current_user": current_user, "photos": photos},
    )


@router.post("/favorites/download")
async def download_favorites(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> Response:
    photo_ids = await favorite_photo_ids(db, current_user)
    photos = await photos_by_ids(db, photo_ids)
    if not photos:
        return RedirectResponse(url="/favorites", status_code=303)

    archive = BytesIO()
    used_names: set[str] = set()
    downloaded_photo_ids = []
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_file:
        for index, photo in enumerate(photos, start=1):
            path = ensure_download_path(photo)
            if path is None:
                continue
            zip_file.write(path, arcname=zip_entry_name(index, photo, used_names))
            downloaded_photo_ids.append(str(photo.id))
            await record_download_history(db, request, current_user, photo)

    if not downloaded_photo_ids:
        return RedirectResponse(url="/favorites", status_code=303)

    await record_activity(
        db,
        request,
        "photo_download",
        user=current_user,
        target_id=",".join(downloaded_photo_ids),
    )
    archive.seek(0)
    filename = f"favorites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
        select(DownloadHistory)
        .where(
            DownloadHistory.user_id == current_user.login_id,
        )
        .order_by(DownloadHistory.downloaded_at.desc(), DownloadHistory.id.desc())
    )
    rows = []
    for history in result.scalars().all():
        for photo in await photos_by_ids(db, [history.photo_id]):
            item = serialize_photo(photo)
            item["downloaded_at_label"] = display_datetime(history.downloaded_at)
            rows.append(item)
    return templates.TemplateResponse(
        "downloads.html",
        {"request": request, "current_user": current_user, "photos": rows},
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    now = datetime.now().astimezone()
    user_count = await scalar_count(db, select(func.count()).select_from(DeptUser))
    published_album_count = await scalar_count(
        db,
        select(func.count())
        .select_from(Album)
        .where(Album.publish_from <= now, Album.publish_to >= now),
    )
    photo_count = await scalar_count(
        db,
        select(func.count()).select_from(Photo).where(Photo.is_deleted.is_(False)),
    )
    tag_count = await scalar_count(db, select(func.count()).select_from(DancerTag))

    album_result = await db.execute(select(Album).order_by(Album.created_at.desc(), Album.id.desc()).limit(2))
    recent_albums = []
    for album in album_result.scalars().all():
        count = await scalar_count(
            db,
            select(func.count()).select_from(Photo).where(
                Photo.album_id == album.id,
                Photo.is_deleted.is_(False),
            ),
        )
        recent_albums.append(
            {
                "id": album.id,
                "title": album.title,
                "status": "公開中" if album.publish_from <= now <= album.publish_to else "非公開",
                "count": count,
            }
        )

    log_result = await db.execute(select(AccessLog).order_by(AccessLog.rireki_no.desc()).limit(20))
    recent_logs = access_log_events(list(log_result.scalars().all()))[:2]
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "stats": {
                "user_count": user_count,
                "published_album_count": published_album_count,
                "photo_count": photo_count,
                "tag_count": tag_count,
            },
            "recent_albums": recent_albums,
            "recent_logs": recent_logs,
        },
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
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(AccessLog).order_by(AccessLog.rireki_no.desc()).limit(200))
    logs = access_log_events(list(result.scalars().all()))[:100]
    return templates.TemplateResponse(
        "admin/logs.html",
        {"request": request, "current_user": current_user, "logs": logs},
    )
