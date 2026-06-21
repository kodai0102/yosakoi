from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.album import Album
from app.models.dept_user import DeptUser
from app.schemas.album import AlbumCreate, AlbumRead, AlbumUpdate
from app.services.albums import (
    display_datetime,
    is_album_published,
    normalize_datetime,
    now_utc,
    serialize_album,
)
from app.services.photos import make_thumbnail, open_image, save_bytes, validate_upload

router = APIRouter(tags=["albums"])
templates = Jinja2Templates(directory="app/templates")


def datetime_local(value: datetime) -> str:
    return display_datetime(value).strftime("%Y-%m-%dT%H:%M")


templates.env.filters["datetime_local"] = datetime_local


def ensure_publish_period(publish_from: datetime, publish_to: datetime) -> None:
    if publish_from > publish_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="公開開始日時は公開終了日時以前にしてください",
        )


def parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="年度は数値で指定してください",
        ) from exc


def album_form_context(
    request: Request,
    current_user: DeptUser,
    album: Album | None,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "request": request,
        "current_user": current_user,
        "album": album,
        "error": error,
    }


def album_form_values(
    year: int,
    event_name: str,
    event_date: date,
    title: str,
    description: str,
    thumbnail_path: str,
    publish_from: datetime,
    publish_to: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=None,
        year=year,
        event_name=event_name,
        event_date=event_date,
        title=title,
        description=description,
        thumbnail_path=thumbnail_path,
        publish_from=publish_from,
        publish_to=publish_to,
    )


async def save_album_thumbnail(file: UploadFile | None) -> str | None:
    if file is None or not file.filename:
        return None
    payload = await file.read()
    validate_upload(file, payload)
    image = open_image(payload)
    object_key = f"album-thumbnails/{uuid4()}.webp"
    save_bytes(object_key, make_thumbnail(image))
    return object_key


def validation_message(exc: ValidationError) -> str:
    first_error = exc.errors()[0] if exc.errors() else {}
    field = first_error.get("loc", ["入力"])[0]
    if field == "year":
        return "年度は1900以上9999以下で入力してください"
    return "入力内容を確認してください"


async def get_album_or_404(db: AsyncSession, album_id: int) -> Album:
    album = await db.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="アルバムが存在しません")
    return album


def album_list_query(q: str | None = None, year: int | None = None):
    query = select(Album)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Album.title.ilike(like), Album.event_name.ilike(like)))
    if year is not None:
        query = query.where(Album.year == year)
    return query.order_by(Album.event_date.desc(), Album.id.desc())


def public_album_list_query(q: str | None = None, year: int | None = None):
    current = now_utc()
    return album_list_query(q, year).where(
        Album.publish_from <= current,
        Album.publish_to >= current,
    )


@router.get("/albums", response_class=HTMLResponse)
async def albums_page(
    request: Request,
    q: str | None = None,
    year: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> HTMLResponse:
    result = await db.execute(public_album_list_query(q, parse_optional_int(year)))
    albums = [serialize_album(album) for album in result.scalars().all()]
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "current_user": current_user,
            "albums": albums,
            "query": q or "",
            "year": year or "",
        },
    )


@router.get("/api/albums")
async def api_list_albums(
    q: str | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> dict[str, object]:
    result = await db.execute(public_album_list_query(q, year))
    albums = result.scalars().all()
    return {"success": True, "data": {"albums": [AlbumRead.model_validate(a) for a in albums]}}


@router.get("/api/albums/{album_id}")
async def api_get_album(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(get_current_user),
) -> dict[str, object]:
    album = await get_album_or_404(db, album_id)
    if not is_album_published(album):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="アルバムが存在しません")
    return {"success": True, "data": {"album": AlbumRead.model_validate(album)}}


@router.get("/admin/albums", response_class=HTMLResponse)
async def admin_albums_page(
    request: Request,
    q: str | None = None,
    year: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(album_list_query(q, parse_optional_int(year)))
    albums = [serialize_album(album) for album in result.scalars().all()]
    return templates.TemplateResponse(
        "admin/albums.html",
        {
            "request": request,
            "current_user": current_user,
            "albums": albums,
            "query": q or "",
            "year": year or "",
        },
    )


@router.get("/admin/albums/new", response_class=HTMLResponse)
async def new_album_page(
    request: Request,
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/album_form.html",
        album_form_context(request, current_user, None),
    )


@router.post("/admin/albums", response_class=HTMLResponse)
async def create_album_form(
    request: Request,
    year: int = Form(...),
    event_name: str = Form(...),
    event_date: date = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    thumbnail_file: UploadFile | None = File(None),
    publish_from: datetime = Form(...),
    publish_to: datetime = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
):
    form_album = album_form_values(
        year,
        event_name,
        event_date,
        title,
        description,
        "",
        publish_from,
        publish_to,
    )
    try:
        thumbnail_path = await save_album_thumbnail(thumbnail_file)
        payload = AlbumCreate(
            year=year,
            event_name=event_name,
            event_date=event_date,
            title=title,
            description=description,
            thumbnail_path=thumbnail_path,
            publish_from=publish_from,
            publish_to=publish_to,
        )
        await create_album(db, payload)
    except ValidationError as exc:
        return templates.TemplateResponse(
            "admin/album_form.html",
            album_form_context(request, current_user, form_album, validation_message(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except HTTPException as exc:
        return templates.TemplateResponse(
            "admin/album_form.html",
            album_form_context(request, current_user, form_album, str(exc.detail)),
            status_code=exc.status_code,
        )
    return RedirectResponse(url="/admin/albums", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/albums/{album_id}/edit", response_class=HTMLResponse)
async def edit_album_page(
    request: Request,
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    album = await get_album_or_404(db, album_id)
    return templates.TemplateResponse(
        "admin/album_form.html",
        album_form_context(request, current_user, album),
    )


@router.post("/admin/albums/{album_id}", response_class=HTMLResponse)
async def update_album_form(
    request: Request,
    album_id: int,
    year: int = Form(...),
    event_name: str = Form(...),
    event_date: date = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    thumbnail_file: UploadFile | None = File(None),
    publish_from: datetime = Form(...),
    publish_to: datetime = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
):
    form_album = album_form_values(
        year,
        event_name,
        event_date,
        title,
        description,
        "",
        publish_from,
        publish_to,
    )
    form_album.id = album_id
    try:
        current_album = await get_album_or_404(db, album_id)
        thumbnail_path = await save_album_thumbnail(thumbnail_file) or current_album.thumbnail_path
        payload = AlbumUpdate(
            year=year,
            event_name=event_name,
            event_date=event_date,
            title=title,
            description=description,
            thumbnail_path=thumbnail_path,
            publish_from=publish_from,
            publish_to=publish_to,
        )
        await update_album(db, album_id, payload)
    except ValidationError as exc:
        return templates.TemplateResponse(
            "admin/album_form.html",
            album_form_context(request, current_user, form_album, validation_message(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except HTTPException as exc:
        return templates.TemplateResponse(
            "admin/album_form.html",
            album_form_context(request, current_user, form_album, str(exc.detail)),
            status_code=exc.status_code,
        )
    return RedirectResponse(url="/admin/albums", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/albums/{album_id}/delete", response_class=HTMLResponse)
async def delete_album_form(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
):
    await delete_album(db, album_id)
    return RedirectResponse(url="/admin/albums", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/admin/albums")
async def api_admin_list_albums(
    q: str | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    result = await db.execute(album_list_query(q, year))
    albums = result.scalars().all()
    return {"success": True, "data": {"albums": [AlbumRead.model_validate(a) for a in albums]}}


@router.post("/api/admin/albums", status_code=status.HTTP_201_CREATED)
async def api_admin_create_album(
    payload: AlbumCreate,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    album = await create_album(db, payload)
    return {"success": True, "data": {"album": AlbumRead.model_validate(album)}}


@router.get("/api/admin/albums/{album_id}")
async def api_admin_get_album(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    album = await get_album_or_404(db, album_id)
    return {"success": True, "data": {"album": AlbumRead.model_validate(album)}}


@router.put("/api/admin/albums/{album_id}")
async def api_admin_update_album(
    album_id: int,
    payload: AlbumUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    album = await update_album(db, album_id, payload)
    return {"success": True, "data": {"album": AlbumRead.model_validate(album)}}


@router.delete("/api/admin/albums/{album_id}")
async def api_admin_delete_album(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    await delete_album(db, album_id)
    return {"success": True, "data": {}}


async def create_album(db: AsyncSession, payload: AlbumCreate) -> Album:
    publish_from = normalize_datetime(payload.publish_from)
    publish_to = normalize_datetime(payload.publish_to)
    ensure_publish_period(publish_from, publish_to)
    album = Album(
        year=payload.year,
        event_name=payload.event_name,
        event_date=payload.event_date,
        title=payload.title,
        description=payload.description,
        thumbnail_path=payload.thumbnail_path,
        publish_from=publish_from,
        publish_to=publish_to,
    )
    db.add(album)
    await db.commit()
    await db.refresh(album)
    return album


async def update_album(db: AsyncSession, album_id: int, payload: AlbumUpdate) -> Album:
    album = await get_album_or_404(db, album_id)
    publish_from = (
        normalize_datetime(payload.publish_from)
        if payload.publish_from is not None
        else normalize_datetime(album.publish_from)
    )
    publish_to = (
        normalize_datetime(payload.publish_to)
        if payload.publish_to is not None
        else normalize_datetime(album.publish_to)
    )
    ensure_publish_period(publish_from, publish_to)

    if payload.year is not None:
        album.year = payload.year
    if payload.event_name is not None:
        album.event_name = payload.event_name
    if payload.event_date is not None:
        album.event_date = payload.event_date
    if payload.title is not None:
        album.title = payload.title
    if payload.description is not None:
        album.description = payload.description
    if payload.thumbnail_path is not None:
        album.thumbnail_path = payload.thumbnail_path
    if payload.publish_from is not None:
        album.publish_from = publish_from
    if payload.publish_to is not None:
        album.publish_to = publish_to

    await db.commit()
    await db.refresh(album)
    return album


async def delete_album(db: AsyncSession, album_id: int) -> None:
    album = await get_album_or_404(db, album_id)
    await db.delete(album)
    await db.commit()
