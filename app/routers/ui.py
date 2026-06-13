from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dependencies.auth import get_current_user, require_admin
from app.models.user import User

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


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


@router.get("/albums", response_class=HTMLResponse)
async def albums_page(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "current_user": current_user, "albums": sample_albums()},
    )


@router.get("/albums/{album_id}", response_class=HTMLResponse)
async def album_photos_page(
    request: Request,
    album_id: int,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "favorites.html",
        {"request": request, "current_user": current_user, "photos": sample_photos()[:6]},
    )


@router.get("/tags", response_class=HTMLResponse)
async def tag_search_page(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "tag_search.html",
        {
            "request": request,
            "current_user": current_user,
            "tags": ["山田太郎", "佐藤花子", "旗士", "煽り", "地方車", "本祭"],
            "photos": sample_photos()[:8],
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "downloads.html",
        {"request": request, "current_user": current_user, "photos": sample_photos()[:5]},
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard_page(
    request: Request,
    current_user: User = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/dashboard.html", {"request": request, "current_user": current_user}
    )


@router.get("/admin/albums", response_class=HTMLResponse)
async def admin_albums_page(
    request: Request,
    current_user: User = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/albums.html",
        {"request": request, "current_user": current_user, "albums": sample_albums()},
    )


@router.get("/admin/albums/{album_id}/photos", response_class=HTMLResponse)
async def admin_photos_page(
    request: Request,
    album_id: int,
    current_user: User = Depends(require_admin),
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
    current_user: User = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/tags.html",
        {
            "request": request,
            "current_user": current_user,
            "tags": ["山田太郎", "佐藤花子", "旗士", "煽り", "地方車", "本祭"],
        },
    )


@router.get("/admin/logs", response_class=HTMLResponse)
async def admin_logs_page(
    request: Request,
    current_user: User = Depends(require_admin),
) -> HTMLResponse:
    logs = [
        {"action": "login_success", "user": "管理者", "at": "2026/06/13 17:10"},
        {"action": "user_create", "user": "管理者", "at": "2026/06/13 17:00"},
        {"action": "photo_upload", "user": "管理者", "at": "2026/06/13 16:42"},
    ]
    return templates.TemplateResponse(
        "admin/logs.html",
        {"request": request, "current_user": current_user, "logs": logs},
    )
