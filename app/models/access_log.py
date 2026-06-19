from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccessLog(Base):
    __tablename__ = "access_log"

    rireki_no: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_name: Mapped[str | None] = mapped_column(String(100))
    user_id: Mapped[str | None] = mapped_column(String(100), index=True)
    logon_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    logoff_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    pic_download_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    pic_download_list: Mapped[str | None] = mapped_column(Text)
    pic_upload_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    pic_upload_list: Mapped[str | None] = mapped_column(Text)
    favorite: Mapped[str | None] = mapped_column(Text)
    operation_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    operation_name: Mapped[str | None] = mapped_column(String(100), index=True)
    operation_target: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (ForeignKeyConstraint(["user_id"], ["dept_user.user_id"]),)
