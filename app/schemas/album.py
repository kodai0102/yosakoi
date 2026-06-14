from datetime import date, datetime

from pydantic import BaseModel, Field


class AlbumCreate(BaseModel):
    year: int = Field(ge=1900, le=9999)
    event_name: str = Field(min_length=1, max_length=100)
    event_date: date
    title: str = Field(min_length=1, max_length=150)
    description: str | None = None
    thumbnail_path: str | None = None
    publish_from: datetime
    publish_to: datetime


class AlbumUpdate(BaseModel):
    year: int | None = Field(default=None, ge=1900, le=9999)
    event_name: str | None = Field(default=None, min_length=1, max_length=100)
    event_date: date | None = None
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    thumbnail_path: str | None = None
    publish_from: datetime | None = None
    publish_to: datetime | None = None


class AlbumRead(BaseModel):
    id: int
    year: int
    event_name: str
    event_date: date
    title: str
    description: str | None
    thumbnail_path: str | None
    publish_from: datetime
    publish_to: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
