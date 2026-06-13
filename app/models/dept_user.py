from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeptUser(Base):
    __tablename__ = "dept_user"

    user_no: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), primary_key=True, unique=True, index=True)
    user_name: Mapped[str] = mapped_column(String(100))
    password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="member", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    create_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def id(self) -> int:
        return self.user_no

    @property
    def login_id(self) -> str:
        return self.user_id

    @property
    def display_name(self) -> str:
        return self.user_name

    @property
    def password_hash(self) -> str:
        return self.password

    @property
    def valid_from(self) -> datetime:
        return self.start_date

    @property
    def valid_to(self) -> datetime:
        return self.end_date

    @property
    def created_at(self) -> datetime:
        return self.create_date
