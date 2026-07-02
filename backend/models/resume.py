from datetime import datetime

from sqlalchemy import Integer, String, ForeignKey, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    basic_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    internship_exp: Mapped[list | None] = mapped_column(JSON, nullable=True)
    project_exp: Mapped[list | None] = mapped_column(JSON, nullable=True)
    personal_strengths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    history: Mapped[list["ResumeHistory"]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class ResumeHistory(Base):
    __tablename__ = "resume_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(Integer, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 历史版本标题
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    resume: Mapped["Resume"] = relationship(back_populates="history")
