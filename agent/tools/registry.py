"""工具注册表 - 管理所有可用工具，含按场景熔断器"""

import logging
import time
from typing import Type

from agent.tools.basetool import BaseTool

logger = logging.getLogger(__name__)

# 熔断器配置
CIRCUIT_BREAKER_THRESHOLD = 3      # 连续失败次数触发熔断
CIRCUIT_BREAKER_COOLDOWN = 300     # 熔断冷却时间（秒）


class ToolRegistry:
    """工具注册表，使用装饰器自动注册工具，含按场景熔断器"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        # 熔断器状态：(tool_name, scenario) → 连续失败次数
        self._failure_counts: dict[tuple[str, str], int] = {}
        # 熔断器状态：(tool_name, scenario) → 禁用截止时间戳
        self._disabled_until: dict[tuple[str, str], float] = {}

    def register(self, tool_class: Type[BaseTool]):
        """装饰器：注册工具类"""
        def decorator(cls):
            instance = cls()
            self._tools[instance.name] = instance
            return cls
        return decorator(tool_class) if tool_class else decorator

    def get(self, name: str) -> BaseTool | None:
        """根据名称获取工具"""
        return self._tools.get(name)

    def _is_tool_available(self, tool: BaseTool, scenario: str) -> bool:
        """判断工具是否在指定场景可用（scenarios 为空或包含 scenario）"""
        return not tool.scenarios or scenario in tool.scenarios

    def is_disabled(self, tool_name: str, scenario: str) -> bool:
        """检查工具在指定场景是否被熔断"""
        key = (tool_name, scenario)
        until = self._disabled_until.get(key, 0)
        if time.time() < until:
            return True
        # 冷却期已过，自动恢复
        if key in self._disabled_until:
            del self._disabled_until[key]
            self._failure_counts[key] = 0
            logger.info("熔断器恢复: %s [%s]", tool_name, scenario)
        return False

    def record_failure(self, tool_name: str, scenario: str) -> None:
        """记录工具失败，连续失败达阈值时触发熔断"""
        key = (tool_name, scenario)
        count = self._failure_counts.get(key, 0) + 1
        self._failure_counts[key] = count

        if count >= CIRCUIT_BREAKER_THRESHOLD:
            self._disabled_until[key] = time.time() + CIRCUIT_BREAKER_COOLDOWN
            logger.warning(
                "熔断器触发: %s [%s] 连续失败 %d 次，禁用 %d 秒",
                tool_name, scenario, count, CIRCUIT_BREAKER_COOLDOWN,
            )

    def record_success(self, tool_name: str, scenario: str) -> None:
        """记录工具成功，重置连续失败计数"""
        key = (tool_name, scenario)
        self._failure_counts[key] = 0

    def get_schemas_by_scenario(self, scenario: str) -> list[dict]:
        """获取指定场景的工具 schema（排除已熔断的工具）"""
        return [
            tool.to_schema()
            for tool in self._tools.values()
            if self._is_tool_available(tool, scenario)
            and not self.is_disabled(tool.name, scenario)
        ]

    def get_tools_by_scenario(self, scenario: str) -> dict[str, BaseTool]:
        """获取指定场景的工具实例（排除已熔断的工具）"""
        return {
            name: tool
            for name, tool in self._tools.items()
            if self._is_tool_available(tool, scenario)
            and not self.is_disabled(name, scenario)
        }

    def get_all_schemas(self) -> list[dict]:
        """获取所有工具的 OpenAI schema"""
        return [tool.to_schema() for tool in self._tools.values()]

    def get_all_names(self) -> list[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())

    def get_all_tools(self) -> dict[str, BaseTool]:
        """获取所有工具实例"""
        return dict(self._tools)

    def reset_circuit_breaker(self, tool_name: str | None = None, scenario: str | None = None) -> None:
        """手动重置熔断器（测试或管理用）"""
        if tool_name and scenario:
            key = (tool_name, scenario)
            self._failure_counts.pop(key, None)
            self._disabled_until.pop(key, None)
        elif tool_name:
            for key in list(self._failure_counts):
                if key[0] == tool_name:
                    self._failure_counts.pop(key, None)
                    self._disabled_until.pop(key, None)
        else:
            self._failure_counts.clear()
            self._disabled_until.clear()


# 全局注册表实例
registry = ToolRegistry()
