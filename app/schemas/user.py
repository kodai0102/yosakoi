from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    login_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(admin|member)$")
    valid_from: datetime
    valid_to: datetime
    is_active: bool = True


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8)
    role: str | None = Field(default=None, pattern="^(admin|member)$")
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    id: int
    login_id: str
    display_name: str
    role: str
    is_active: bool
    valid_from: datetime
    valid_to: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
