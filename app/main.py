from fastapi import FastAPI, HTTPException

from app.exception_handlers import http_exception_handler
from app.middleware.auth_period import auth_period_middleware
from app.routers.admin_users import router as admin_users_router
from app.routers.albums import router as albums_router
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.photos import router as photos_router
from app.routers.ui import router as ui_router


def create_app() -> FastAPI:
    app = FastAPI(title="YOSAKOI PHOTO ARCHIVE")
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.middleware("http")(auth_period_middleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_users_router)
    app.include_router(photos_router)
    app.include_router(albums_router)
    app.include_router(ui_router)
    return app


app = create_app()
