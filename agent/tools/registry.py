"""工具注册表 - 管理所有可用工具"""

from typing import Type
from agent.tools.basetool import BaseTool


class ToolRegistry:
    """工具注册表，使用装饰器自动注册工具"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

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

    def get_schemas_by_scenario(self, scenario: str) -> list[dict]:
        """获取指定场景的工具 schema"""
        return [
            tool.to_schema()
            for tool in self._tools.values()
            if self._is_tool_available(tool, scenario)
        ]

    def get_tools_by_scenario(self, scenario: str) -> dict[str, BaseTool]:
        """获取指定场景的工具实例"""
        return {
            name: tool
            for name, tool in self._tools.items()
            if self._is_tool_available(tool, scenario)
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


# 全局注册表实例
registry = ToolRegistry()
