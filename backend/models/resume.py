from datetime import datetime

from sqlalchemy import Integer, String, ForeignKey, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Resume(Base):
    """简历模型 — 每个版本一行，同一 user_id 可有多行"""
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 版本名称
    basic_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    internship_exp: Mapped[list | None] = mapped_column(JSON, nullable=True)
    project_exp: Mapped[list | None] = mapped_column(JSON, nullable=True)
    personal_strengths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
