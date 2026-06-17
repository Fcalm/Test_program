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

    # === 工具结果缓存 ===
    tool_results: dict[str, Any] = field(default_factory=dict)

    # === 对话阶段 ===
    stage: str = ""

    # === 错误与统计 ===
    error: str | None = None
    usage: dict = field(default_factory=dict)

    # === 压缩统计 ===
    compact_count: int = 0

    # === 消息操作 ===

    def add_message(self, role: str, content: str | None, **kwargs) -> None:
        """添加消息到历史"""
        msg = {"role": role, "content": content, **kwargs}
        self.messages.append(msg)

    # === 工具结果操作 ===

    def set_tool_result(self, tool_name: str, result: Any) -> None:
        """缓存工具执行结果"""
        self.tool_results[tool_name] = result

    def get_tool_result(self, tool_name: str) -> Any | None:
        """获取缓存的工具结果"""
        return self.tool_results.get(tool_name)

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

    def snapshot(self) -> dict:
        """导出可序列化的状态快照，用于持久化到数据库"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "scenario": self.scenario,
            "stage": self.stage,
            "messages": self.messages,
            "tool_results": self.tool_results,
            "turn_count": self.turn_count,
            "usage": self.usage,
            "error": self.error,
            "compact_count": self.compact_count,
        }

    @classmethod
    def restore(cls, data: dict) -> AgentState:
        """从快照恢复状态"""
        return cls(
            session_id=data["session_id"],
            user_id=data.get("user_id"),
            scenario=data.get("scenario", ""),
            stage=data.get("stage", ""),
            messages=data.get("messages", []),
            tool_results=data.get("tool_results", {}),
            turn_count=data.get("turn_count", 0),
            usage=data.get("usage", {}),
            error=data.get("error"),
            compact_count=data.get("compact_count", 0),
        )
