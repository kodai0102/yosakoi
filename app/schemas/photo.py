from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PhotoRead(BaseModel):
    id: UUID
    album_id: int
    original_path: str
    thumbnail_path: str
    file_name: str
    content_type: str
    file_size: int
    taken_at: datetime
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
