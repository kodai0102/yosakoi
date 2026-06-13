from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import get_settings


settings = get_settings()


async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    if exc.status_code in {401, 403}:
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(key=settings.auth_cookie_name)
        return response

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )
