"""用户上传文件模型"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf / docx
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # 字节数
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 提取的文本
    char_count: Mapped[int] = mapped_column(Integer, default=0)  # 文本字符数
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
