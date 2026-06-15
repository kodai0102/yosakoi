from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.access_log import AccessLog
from app.models.dept_user import DeptUser
from app.routers.albums import get_album_or_404
from app.schemas.album import AlbumRead
from app.schemas.photo import PhotoRead
from app.services.activity_logs import record_activity
from app.services.albums import is_album_published, serialize_album
from app.services.photos import (
    create_photo,
    get_photo_or_404,
    list_album_photos,
    logical_delete_photo,
    media_path,
    serialize_photo,
    storage_root,
)
from app.services.tags import get_photo_tag_names, get_photo_tags_map, parse_tag_names, set_photo_tags

router = APIRouter(tags=["photos"])
templates = Jinja2Templates(directory="app/templates")
UNFAVORITE_PREFIX = "unfavorite:"


def serialize_photos(photos: list[object]) -> list[dict[str, object]]:
    return [serialize_photo(photo) for photo in photos]


async def serialize_photos_with_tags(db: AsyncSession, photos: list[object]) -> list[dict[str, object]]:
    tag_map = await get_photo_tags_map(db, [photo.id for photo in photos])
    rows = []
    for photo in photos:
        item = serialize_photo(photo)
        item["tags"] = tag_map.get(photo.id, [])
        item["tags_text"] = ", ".join(item["tags"])
        rows.append(item)
    return rows


def ensure_media_path(object_path: str) -> Path:
    root = storage_root().resolve()
    path = media_path(object_path).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画像が存在しません")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画像が存在しません")
    return path


async def is_favorite_photo(db: AsyncSession, user: DeptUser, photo_id: UUID) -> bool:
    favorite_id = str(photo_id)
    result = await db.execute(
        select(AccessLog.favorite)
        .where(
            AccessLog.user_id == user.login_id,
            AccessLog.favorite.in_([favorite_id, f"{UNFAVORITE_PREFIX}{favorite_id}"]),
        )
        .order_by(AccessLog.rireki_no.desc())
        .limit(1)
    )
    return result.scalar_one_or_none() == favorite_id


@router.get("/media/{object_path:path}")
async def media_file(
    object_path: str,
    current_user: DeptUser = Depends(get_current_user),
) -> FileResponse:
    path = ensure_media_path(object_path)
    media_type = "image/webp" if path.suffix == ".webp" else None
    return FileResponse(path, media_type=media_type)


@router.get("/albums/{album_id}", response_class=HTMLResponse)
async def album_photos_page(
    request: Request,
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    album = await get_album_or_404(db, album_id)
    if not is_album_published(album):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="アルバムが存在しません")
    photos = await list_album_photos(db, album.id)
    album_data = serialize_album(album)
    album_data["count"] = len(photos)
    return templates.TemplateResponse(
        "album_photos.html",
        {
            "request": request,
            "current_user": current_user,
            "album": album_data,
            "photos": serialize_photos(photos),
        },
    )


@router.get("/photos/{photo_id}", response_class=HTMLResponse)
async def photo_detail_page(
    request: Request,
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    photo = await get_photo_or_404(db, photo_id)
    album = await get_album_or_404(db, photo.album_id)
    if not is_album_published(album) and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="写真が存在しません")
    album_data = serialize_album(album)
    photo_data = serialize_photo(photo)
    photo_data["is_favorite"] = await is_favorite_photo(db, current_user, photo.id)
    photo_data["tags"] = await get_photo_tag_names(db, photo.id)
    return templates.TemplateResponse(
        "photo_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "album": album_data,
            "photo": photo_data,
        },
    )


@router.get("/admin/albums/{album_id}/photos", response_class=HTMLResponse)
async def admin_photos_page(
    request: Request,
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    album = await get_album_or_404(db, album_id)
    photos = await list_album_photos(db, album.id)
    album_data = serialize_album(album)
    album_data["count"] = len(photos)
    return templates.TemplateResponse(
        "admin/photos.html",
        {
            "request": request,
            "current_user": current_user,
            "album": album_data,
            "photos": await serialize_photos_with_tags(db, photos),
            "error": None,
        },
    )


@router.post("/admin/albums/{album_id}/photos", response_class=HTMLResponse)
async def upload_photos_form(
    request: Request,
    album_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> RedirectResponse:
    album = await get_album_or_404(db, album_id)
    photos = []
    for file in files:
        photos.append(await create_photo(db, album, file))
    await record_activity(
        db,
        request,
        "photo_upload",
        user=current_user,
        target_id=",".join(str(photo.id) for photo in photos),
    )
    return RedirectResponse(
        url=f"/admin/albums/{album_id}/photos",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/photos/{photo_id}/delete", response_class=HTMLResponse)
async def delete_photo_form(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> RedirectResponse:
    photo = await get_photo_or_404(db, photo_id)
    album_id = photo.album_id
    await delete_photo(db, photo_id)
    return RedirectResponse(
        url=f"/admin/albums/{album_id}/photos",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/photos/{photo_id}/tags", response_class=HTMLResponse)
async def update_photo_tags_form(
    photo_id: UUID,
    tags: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> RedirectResponse:
    photo = await get_photo_or_404(db, photo_id)
    await set_photo_tags(db, photo_id, parse_tag_names(tags))
    return RedirectResponse(
        url=f"/admin/albums/{photo.album_id}/photos",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/photos/{photo_id}/favorite", response_class=HTMLResponse)
async def favorite_photo_form(
    request: Request,
    photo_id: UUID,
    redirect_to: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> RedirectResponse:
    await get_photo_or_404(db, photo_id)
    if await is_favorite_photo(db, current_user, photo_id):
        await record_activity(db, request, "favorite_remove", user=current_user, target_id=str(photo_id))
    else:
        await record_activity(db, request, "favorite", user=current_user, target_id=str(photo_id))
    return RedirectResponse(
        url=redirect_to or f"/photos/{photo_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/photos/{photo_id}/download")
async def download_photo_form(
    request: Request,
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> FileResponse:
    photo = await get_photo_or_404(db, photo_id)
    album = await get_album_or_404(db, photo.album_id)
    if not is_album_published(album) and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="写真が存在しません")
    await record_activity(db, request, "photo_download", user=current_user, target_id=str(photo_id))
    path = ensure_media_path(photo.original_path)
    return FileResponse(
        path,
        filename=photo.file_name,
        media_type=photo.content_type,
    )


@router.get("/api/albums/{album_id}/photos")
async def api_list_album_photos(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> dict[str, object]:
    album = await get_album_or_404(db, album_id)
    if not is_album_published(album):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="アルバムが存在しません")
    photos = await list_album_photos(db, album.id)
    return {
        "success": True,
        "data": {
            "album": AlbumRead.model_validate(album),
            "photos": [PhotoRead.model_validate(photo) for photo in photos],
        },
    }


@router.get("/api/photos/{photo_id}")
async def api_get_photo(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> dict[str, object]:
    photo = await get_photo_or_404(db, photo_id)
    album = await get_album_or_404(db, photo.album_id)
    if not is_album_published(album) and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="写真が存在しません")
    return {"success": True, "data": {"photo": PhotoRead.model_validate(photo)}}


@router.post("/api/admin/albums/{album_id}/photos", status_code=status.HTTP_201_CREATED)
async def api_admin_upload_photos(
    request: Request,
    album_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    album = await get_album_or_404(db, album_id)
    photos = [await create_photo(db, album, file) for file in files]
    await record_activity(
        db,
        request,
        "photo_upload",
        user=current_user,
        target_id=",".join(str(photo.id) for photo in photos),
    )
    return {
        "success": True,
        "data": {"photos": [PhotoRead.model_validate(photo) for photo in photos]},
    }


@router.delete("/api/admin/photos/{photo_id}")
async def api_admin_delete_photo(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    await delete_photo(db, photo_id)
    return {"success": True, "data": {}}


async def delete_photo(db: AsyncSession, photo_id: UUID):
    return await logical_delete_photo(db, photo_id)
