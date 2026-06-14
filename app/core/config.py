from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "yosakoi"
    postgres_user: str = "yosakoi"
    postgres_password: str = "yosakoi"
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    auth_cookie_name: str = "access_token"
    local_storage_root: str = "storage"
    initial_admin_login_id: str = "admin"
    initial_admin_display_name: str = "管理者"
    initial_admin_password: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
