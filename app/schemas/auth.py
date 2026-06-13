from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login_id: str = Field(min_length=1)
    password: str = Field(min_length=1)
