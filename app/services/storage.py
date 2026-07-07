from functools import lru_cache
from mimetypes import guess_type
from pathlib import Path

import boto3
from botocore.config import Config
from fastapi import HTTPException, status

from app.core.config import get_settings


def storage_backend() -> str:
    return get_settings().storage_backend.lower()


def uses_r2_storage() -> bool:
    return storage_backend() == "r2"


def storage_root() -> Path:
    return Path(get_settings().local_storage_root)


def media_path(object_key: str) -> Path:
    return storage_root() / object_key


def guess_media_type(object_key: str, fallback: str | None = None) -> str | None:
    return fallback or guess_type(object_key)[0]


@lru_cache
def r2_client():
    settings = get_settings()
    required = {
        "R2_ACCOUNT_ID": settings.r2_account_id,
        "R2_ACCESS_KEY_ID": settings.r2_access_key_id,
        "R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
        "R2_BUCKET": settings.r2_bucket,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"R2設定が不足しています: {', '.join(missing)}")

    endpoint_url = (
        settings.r2_endpoint_url
        or f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def save_object(object_key: str, payload: bytes, content_type: str | None = None) -> None:
    if uses_r2_storage():
        r2_client().put_object(
            Bucket=get_settings().r2_bucket,
            Key=object_key,
            Body=payload,
            ContentType=guess_media_type(object_key, content_type) or "application/octet-stream",
        )
        return

    path = media_path(object_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def read_object(object_key: str) -> tuple[bytes, str | None]:
    if uses_r2_storage():
        try:
            response = r2_client().get_object(Bucket=get_settings().r2_bucket, Key=object_key)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="画像が存在しません",
            ) from exc
        return response["Body"].read(), response.get("ContentType")

    root = storage_root().resolve()
    path = media_path(object_key).resolve()
    if root not in path.parents or not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画像が存在しません")
    return path.read_bytes(), guess_media_type(object_key)


def object_exists(object_key: str) -> bool:
    if uses_r2_storage():
        try:
            r2_client().head_object(Bucket=get_settings().r2_bucket, Key=object_key)
            return True
        except Exception:
            return False

    root = storage_root().resolve()
    path = media_path(object_key).resolve()
    return root in path.parents and path.exists() and path.is_file()


def delete_object(object_key: str | None) -> None:
    if not object_key:
        return

    if uses_r2_storage():
        r2_client().delete_object(Bucket=get_settings().r2_bucket, Key=object_key)
        return

    root = storage_root().resolve()
    path = media_path(object_key).resolve()
    if root in path.parents and path.exists() and path.is_file():
        path.unlink()


def presigned_object_url(
    object_key: str,
    expires_in: int = 600,
    content_type: str | None = None,
) -> str:
    if not uses_r2_storage():
        raise RuntimeError("Presigned URLはR2ストレージでのみ利用できます")

    params = {
        "Bucket": get_settings().r2_bucket,
        "Key": object_key,
    }
    if content_type:
        params["ResponseContentType"] = content_type

    return r2_client().generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
    )
