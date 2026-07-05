"""Agent 会话状态模型"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AgentSession(Base):
    """Agent 会话状态表

    存储 Agent 对话的完整状态，支持跨天恢复会话。
    """
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scenario: Mapped[str] = mapped_column(String(20), nullable=False)  # resume/interview/job_find/analysis
    title: Mapped[str] = mapped_column(String(200), nullable=True, default="")  # 会话标题

    # JSON 字段存储复杂数据
    messages: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON 字符串
    key_data: Mapped[str] = mapped_column(Text, nullable=True, default="{}")  # JSON 字符串
    uploaded_file_ids: Mapped[str] = mapped_column(Text, nullable=True, default="[]")  # JSON 字符串，已注入文件 ID
    summary: Mapped[str] = mapped_column(Text, nullable=True, default="")  # 滚动摘要（工作笔记）

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
