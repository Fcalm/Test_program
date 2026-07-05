"""Agent 引擎状态模型

存储 Agent Loop 需要跨请求保留的引擎状态（滚动摘要 token checkpoint）。
与 agent_sessions 1:1 关系，通过 session_id 关联。
"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AgentLoopState(Base):
    """Agent 引擎状态表

    存储滚动摘要机制需要的跨请求状态：
    - usage: 累计 token 统计（滚动摘要 checkpoint 依赖它）
    - summary_token_checkpoint: 上次更新滚动摘要时的累计 token 数
    - summary_update_count: 滚动摘要更新次数（用于触发记忆提炼）

    与 agent_sessions 是 1:1 关系。
    """
    __tablename__ = "agent_loop_state"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_sessions.id"), primary_key=True
    )
    usage: Mapped[str] = mapped_column(Text, nullable=True, default="{}")  # JSON 字符串
    summary_token_checkpoint: Mapped[int] = mapped_column(Integer, default=0)
    summary_update_count: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
