"""用户上传文件模型"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf / docx
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # 字节数
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关联提取的文本
    text: Mapped["FileText | None"] = relationship(back_populates="file", cascade="all, delete-orphan")


class FileText(Base):
    __tablename__ = "file_texts"

    file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id"), primary_key=True)
    raw_text: Mapped[str] = mapped_column(nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 反向关联
    file: Mapped["UploadedFile"] = relationship(back_populates="text")
