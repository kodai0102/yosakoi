from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    event_name: Mapped[str] = mapped_column(String(100), index=True)
    event_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    publish_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    publish_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
