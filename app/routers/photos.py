from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.access_log import AccessLog
from app.models.dept_user import DeptUser
from app.models.photo import Photo
from app.routers.albums import get_album_or_404
from app.schemas.album import AlbumRead
from app.schemas.photo import PhotoRead
from app.services.activity_logs import record_activity
from app.services.albums import is_album_published, serialize_album
from app.services.downloads import image_file_type, record_download_history
from app.services.photos import (
    create_photo,
    get_photo_or_404,
    list_album_photos,
    logical_delete_photo,
    make_save_jpeg,
    save_jpeg_key_from_original,
    serialize_photo,
)
from app.services.tags import (
    add_tags_to_photos,
    get_photo_tag_names,
    get_photo_tags_map,
    parse_tag_names,
    set_photo_tags,
)
from app.services.storage import (
    guess_media_type,
    media_path,
    object_exists,
    presigned_object_url,
    read_object,
    save_object,
    storage_root,
    uses_r2_storage,
)

router = APIRouter(tags=["photos"])
templates = Jinja2Templates(directory="app/templates")
UNFAVORITE_PREFIX = "unfavorite:"


def serialize_photos(photos: list[object]) -> list[dict[str, object]]:
    return [serialize_photo(photo) for photo in photos]


async def favorite_photo_id_set(db: AsyncSession, user: DeptUser, photo_ids: list[UUID]) -> set[UUID]:
    if not photo_ids:
        return set()

    favorite_values = [str(photo_id) for photo_id in photo_ids]
    target_values = favorite_values + [f"{UNFAVORITE_PREFIX}{photo_id}" for photo_id in favorite_values]
    result = await db.execute(
        select(AccessLog.favorite)
        .where(
            AccessLog.user_id == user.login_id,
            AccessLog.favorite.in_(target_values),
        )
        .order_by(AccessLog.rireki_no.desc())
    )
    states: dict[UUID, bool] = {}
    for value in result.scalars().all():
        if not value:
            continue
        is_removed = value.startswith(UNFAVORITE_PREFIX)
        raw_id = value.removeprefix(UNFAVORITE_PREFIX)
        try:
            photo_id = UUID(raw_id)
        except ValueError:
            continue
        if photo_id not in states:
            states[photo_id] = not is_removed
    return {photo_id for photo_id, is_active in states.items() if is_active}


async def serialize_photos_with_favorites(
    db: AsyncSession,
    photos: list[Photo],
    user: DeptUser,
) -> list[dict[str, object]]:
    favorite_ids = await favorite_photo_id_set(db, user, [photo.id for photo in photos])
    rows = []
    for photo in photos:
        item = serialize_photo(photo)
        item["is_favorite"] = photo.id in favorite_ids
        rows.append(item)
    return rows


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


def image_response(object_path: str, media_type: str | None = None) -> Response:
    payload, stored_media_type = read_object(object_path)
    return Response(
        payload,
        media_type=guess_media_type(object_path, media_type or stored_media_type),
    )


def photo_media_type(photo: Photo) -> str:
    if photo.content_type and photo.content_type.startswith("image/"):
        return photo.content_type
    return guess_media_type(photo.file_name, guess_media_type(photo.original_path))


def inline_image_response(photo: Photo) -> Response:
    image_file_type(photo)
    media_type = photo_media_type(photo)
    if uses_r2_storage():
        response = image_response(
            photo.original_path,
            media_type=media_type,
        )
    else:
        path = ensure_media_path(photo.original_path)
        response = FileResponse(
            path,
            media_type=media_type,
        )
    return response


def photo_save_url(photo: Photo) -> str:
    if uses_r2_storage():
        save_key = ensure_save_jpeg_object(photo)
        return presigned_object_url(
            save_key,
            content_type="image/jpeg",
        )
    return f"/photos/{photo.id}/save-file"


def ensure_save_jpeg_object(photo: Photo) -> str:
    save_key = save_jpeg_key_from_original(photo.original_path)
    if object_exists(save_key):
        return save_key

    payload, _ = read_object(photo.original_path)
    save_object(save_key, make_save_jpeg(payload), "image/jpeg")
    return save_key


def ensure_media_object(object_path: str) -> None:
    if uses_r2_storage():
        if not object_exists(object_path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画像が存在しません")
        return
    ensure_media_path(object_path)


@router.get("/media/{object_path:path}")
async def media_file(
    object_path: str,
    current_user: DeptUser = Depends(get_current_user),
) -> Response:
    if uses_r2_storage():
        return image_response(object_path)
    path = ensure_media_path(object_path)
    media_type = "image/webp" if path.suffix == ".webp" else None
    return FileResponse(path, media_type=media_type)


async def record_and_redirect_to_save(
    request: Request,
    photo_id: UUID,
    db: AsyncSession,
    current_user: DeptUser,
) -> RedirectResponse:
    photo = await get_photo_or_404(db, photo_id)
    album = await get_album_or_404(db, photo.album_id)
    if not is_album_published(album) and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="写真が存在しません")
    await record_download_history(db, request, current_user, photo)
    await record_activity(db, request, "photo_download", user=current_user, target_id=str(photo_id))
    ensure_media_object(photo.original_path)
    return RedirectResponse(url=f"/photos/{photo_id}/save", status_code=status.HTTP_303_SEE_OTHER)


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
            "photos": await serialize_photos_with_favorites(db, photos, current_user),
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


@router.post("/admin/albums/{album_id}/photos/tags/bulk", response_class=HTMLResponse)
async def bulk_update_photo_tags_form(
    album_id: int,
    photo_ids: list[UUID] = Form(default=[]),
    tags: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> RedirectResponse:
    await get_album_or_404(db, album_id)
    tag_names = parse_tag_names(tags)
    if photo_ids and tag_names:
        result = await db.execute(
            select(Photo.id).where(
                Photo.album_id == album_id,
                Photo.is_deleted.is_(False),
                Photo.id.in_(photo_ids),
            )
        )
        valid_photo_ids = list(result.scalars().all())
        await add_tags_to_photos(db, valid_photo_ids, tag_names)
    return RedirectResponse(
        url=f"/admin/albums/{album_id}/photos",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/photos/{photo_id}/favorite", response_class=HTMLResponse)
async def favorite_photo_form(
    request: Request,
    photo_id: UUID,
    redirect_to: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> Response:
    await get_photo_or_404(db, photo_id)
    was_favorite = await is_favorite_photo(db, current_user, photo_id)
    if was_favorite:
        await record_activity(db, request, "favorite_remove", user=current_user, target_id=str(photo_id))
    else:
        await record_activity(db, request, "favorite", user=current_user, target_id=str(photo_id))
    is_favorite = not was_favorite
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"is_favorite": is_favorite})
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
) -> RedirectResponse:
    return await record_and_redirect_to_save(
        request=request,
        photo_id=photo_id,
        db=db,
        current_user=current_user,
    )


@router.get("/photos/{photo_id}/download")
async def download_photo_link(
    request: Request,
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> RedirectResponse:
    return await record_and_redirect_to_save(
        request=request,
        photo_id=photo_id,
        db=db,
        current_user=current_user,
    )


@router.get("/photos/{photo_id}/save", response_class=HTMLResponse)
async def save_photo_page(
    request: Request,
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    photo = await get_photo_or_404(db, photo_id)
    album = await get_album_or_404(db, photo.album_id)
    if not is_album_published(album) and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="写真が存在しません")
    return templates.TemplateResponse(
        "photo_save.html",
        {
            "request": request,
            "current_user": current_user,
            "album": serialize_album(album),
            "photo": serialize_photo(photo),
            "save_image_url": photo_save_url(photo),
        },
    )


@router.get("/photos/{photo_id}/save-file")
async def save_photo_file(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> FileResponse:
    photo = await get_photo_or_404(db, photo_id)
    album = await get_album_or_404(db, photo.album_id)
    if not is_album_published(album) and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="写真が存在しません")
    return inline_image_response(photo)


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
