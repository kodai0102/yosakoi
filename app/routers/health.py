from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.db.session import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def database_health_check() -> JSONResponse:
    try:
        is_connected = await check_database_connection()
    except Exception:
        is_connected = False

    if not is_connected:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ng", "database": "unavailable"},
        )

    return JSONResponse(content={"status": "ok", "database": "available"})
