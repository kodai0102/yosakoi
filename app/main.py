from fastapi import FastAPI

from app.middleware.auth_period import auth_period_middleware
from app.routers.admin_users import router as admin_users_router
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="YOSAKOI PHOTO ARCHIVE")
    app.middleware("http")(auth_period_middleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_users_router)
    return app


app = create_app()
