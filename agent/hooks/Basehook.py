"""Hook 基类定义"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.core.state import AgentState


class BaseHook(ABC):
    """Hook 基类

    所有 hook 必须继承此类并实现 execute 方法。
    Hook 在 Agent 循环的特定时机被调用，用于执行副作用或状态检查。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Hook 名称，用于日志和调试"""
        ...

    @abstractmethod
    async def should_trigger(self, state: AgentState) -> bool:
        """判断是否应该触发此 hook

        Args:
            state: 当前 Agent 状态

        Returns:
            True 表示应该触发，False 表示跳过
        """
        ...

    @abstractmethod
    async def execute(self, state: AgentState) -> AgentState | None:
        """执行 hook 逻辑

        Args:
            state: 当前 Agent 状态

        Returns:
            修改后的状态，或 None 表示不修改状态
        """
        ...

    async def run(self, state: AgentState) -> AgentState | None:
        """运行 hook（先检查是否触发，再执行）

        Args:
            state: 当前 Agent 状态

        Returns:
            修改后的状态，或 None 表示不修改状态
        """
        if await self.should_trigger(state):
            return await self.execute(state)
        return None
