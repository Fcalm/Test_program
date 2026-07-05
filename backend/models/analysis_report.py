"""面试分析报告模型"""

from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from backend.database import Base


class AnalysisReport(Base):
    """面试分析报告"""

    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(index=True, comment="关联的面试会话ID")
    report_data: Mapped[dict] = mapped_column(JSON, nullable=False, comment="分析报告JSON")
    status: Mapped[str] = mapped_column(String(20), default="in_progress", comment="报告状态：in_progress/completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
