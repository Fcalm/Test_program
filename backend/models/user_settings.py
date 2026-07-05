"""用户 LLM 配置"""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True
    )

    # LLM 提供商选择（对应 config.yaml 中的 provider key）
    provider: Mapped[str] = mapped_column(String(50), default="deepseek")

    # 用户自己的 API Key（加密存储）
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 选择的模型 ID
    model: Mapped[str] = mapped_column(String(100), default="")

    # 高级模型 ID
    higher_model: Mapped[str] = mapped_column(String(100), default="")

    # 场景配置覆盖（JSON 字符串）
    scenario_overrides: Mapped[str] = mapped_column(
        String(2000), default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationship
    user = relationship("User", backref="settings")