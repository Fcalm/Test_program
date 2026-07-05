"""Agent 对话状态管理"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Agent 对话状态

    设计原则：
    - 状态与配置分离：max_turn_count 从 AGENT_CONFIGS 读取
    - 可序列化：支持 snapshot/restore 持久化到数据库
    """

    # === 核心状态 ===
    messages: list[dict] = field(default_factory=list)
    turn_count: int = 0

    # === 场景与身份 ===
    scenario: str = ""
    user_id: int | None = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # === 关键数据缓存 ===
    key_data: dict[str, Any] = field(default_factory=dict)

    # === 文件 ===
    uploaded_file_ids: list[int] = field(default_factory=list)    # 已注入文件，持久累积

    # === 会话信息 ===
    title: str = ""  # 会话标题

    # === 错误与统计 ===
    error: str | None = None
    usage: dict = field(default_factory=dict)

    # === 滚动摘要 ===
    summary: str = ""           # 滚动摘要（每次更新覆盖）
    summary_token_checkpoint: int = 0  # 上次摘要更新时的累计 token 数
    summary_update_count: int = 0  # 滚动摘要更新次数（用于触发记忆提炼）

    # === 压缩统计 ===
    compact_count: int = 0

    # === 消息操作 ===

    def add_message(self, role: str, content: str | None, **kwargs) -> None:
        """添加消息到历史"""
        msg = {"role": role, "content": content, **kwargs}
        self.messages.append(msg)

    # === 关键数据操作 ===

    def set_key_data(self, key: str, value: Any) -> None:
        """缓存关键数据"""
        self.key_data[key] = value

    def get_key_data(self, key: str) -> Any | None:
        """获取缓存的关键数据"""
        return self.key_data.get(key)

    # === 轮次控制 ===

    def increment_turn(self) -> None:
        """增加工具调用轮次"""
        self.turn_count += 1

    def increment_compact(self) -> None:
        """增加压缩次数"""
        self.compact_count += 1

    # === 错误处理 ===

    def set_error(self, error: str) -> None:
        """设置错误信息"""
        self.error = error

    def clear_error(self) -> None:
        """清除错误信息"""
        self.error = None

    # === 序列化 ===

    def snapshot_session(self) -> dict:
        """导出会话恢复数据（写 agent_sessions 表）"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "scenario": self.scenario,
            "title": self.title,
            "messages": self.messages,
            "key_data": self.key_data,
            "uploaded_file_ids": self.uploaded_file_ids,
            "summary": self.summary,
        }

    def snapshot_loop(self) -> dict:
        """导出引擎状态数据（写 agent_loop_state 表）"""
        return {
            "session_id": self.session_id,
            "usage": self.usage,
            "summary_token_checkpoint": self.summary_token_checkpoint,
            "summary_update_count": self.summary_update_count,
        }

    @classmethod
    def restore(cls, session_data: dict, loop_data: dict | None = None) -> AgentState:
        """从两张表恢复状态

        Args:
            session_data: agent_sessions 表数据（必须）
            loop_data: agent_loop_state 表数据（可选，首次请求时为空）

        Raises:
            ValueError: 必要字段缺失或类型错误
        """
        if not session_data.get("session_id"):
            raise ValueError("快照数据缺少 session_id")

        messages = session_data.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError(f"messages 类型错误：期望 list，实际 {type(messages).__name__}")

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"messages[{i}] 类型错误：期望 dict，实际 {type(msg).__name__}")
            if "role" not in msg:
                raise ValueError(f"messages[{i}] 缺少 role 字段")

        loop = loop_data or {}

        return cls(
            session_id=session_data["session_id"],
            user_id=session_data.get("user_id"),
            scenario=session_data.get("scenario", ""),
            title=session_data.get("title", ""),
            messages=messages,
            key_data=session_data.get("key_data", {}),
            uploaded_file_ids=session_data.get("uploaded_file_ids", []),
            summary=session_data.get("summary", ""),
            usage=loop.get("usage", {}),
            summary_token_checkpoint=loop.get("summary_token_checkpoint", 0),
            summary_update_count=loop.get("summary_update_count", 0),
        )

    # 向后兼容：旧代码可能仍调用 snapshot()
    def snapshot(self) -> dict:
        """向后兼容：合并 session + loop 数据为单个 dict"""
        data = self.snapshot_session()
        data.update(self.snapshot_loop())
        data["turn_count"] = self.turn_count
        data["error"] = self.error
        data["compact_count"] = self.compact_count
        return data
