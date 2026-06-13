from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.services.activity_logs import record_activity
from app.services.auth import authenticate_user, create_access_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.auth_cookie_name)


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "home.html", {"request": request, "current_user": current_user}
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    login_id: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, login_id, password)
    if user is None:
        await record_activity(
            db,
            request,
            "login_failed",
            user_name=login_id,
            target_type="user",
            target_id=login_id,
        )
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "ログインIDまたはパスワードを確認してください"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    await record_activity(db, request, "login_success", user=user)
    response = RedirectResponse(
        url="/admin/users" if user.role == "admin" else "/",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_auth_cookie(response, create_access_token(user))
    return response


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await record_activity(db, request, "logout", user=current_user)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_auth_cookie(response)
    return response


@router.post("/api/auth/login")
async def api_login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    user = await authenticate_user(db, payload.login_id, payload.password)
    if user is None:
        await record_activity(
            db,
            request,
            "login_failed",
            user_name=payload.login_id,
            target_type="user",
            target_id=payload.login_id,
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "success": False,
                "error": {
                    "code": "unauthorized",
                    "message": "ログインIDまたはパスワードを確認してください",
                },
            },
        )

    await record_activity(db, request, "login_success", user=user)
    response = JSONResponse(
        content={
            "success": True,
            "data": {
                "user": {
                    "id": user.id,
                    "login_id": user.login_id,
                    "display_name": user.display_name,
                    "role": user.role,
                }
            },
        }
    )
    set_auth_cookie(response, create_access_token(user))
    return response


@router.post("/api/auth/logout")
async def api_logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await record_activity(db, request, "logout", user=current_user)
    response = JSONResponse(content={"success": True, "data": {}})
    clear_auth_cookie(response)
    return response


@router.get("/api/auth/me")
async def api_me(current_user: User = Depends(get_current_user)) -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "user": {
                "id": current_user.id,
                "login_id": current_user.login_id,
                "display_name": current_user.display_name,
                "role": current_user.role,
            }
        },
    }
