from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.auth import create_access_token, decode_access_token, get_user_by_id, is_user_available


settings = get_settings()

PUBLIC_PATHS = {
    "/health",
    "/health/db",
    "/login",
    "/api/auth/login",
    "/docs",
    "/openapi.json",
}

LOGOUT_PATHS = {
    "/logout",
    "/api/auth/logout",
}


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/docs/") or path.startswith("/static/")


async def auth_period_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if is_public_path(request.url.path):
        return await call_next(request)

    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return await call_next(request)

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return unauthorized_response(request)

    async with AsyncSessionLocal() as db:
        user = await get_user_by_id(db, int(payload["sub"]))
        if user is None or not is_user_available(user):
            return unauthorized_response(request)

    response = await call_next(request)
    if request.url.path in LOGOUT_PATHS:
        return response

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_access_token(user),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
    )
    return response


def unauthorized_response(request: Request) -> Response:
    if request.url.path.startswith("/api/"):
        response = JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "error": {"code": "account_expired", "message": "利用期間外です"},
            },
        )
    else:
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=settings.auth_cookie_name)
    return response
