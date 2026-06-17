"""工具基类 - 定义工具的标准接口"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """工具基类，所有工具必须继承此类"""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        pass

    @property
    @abstractmethod
    def max_results_chars(self) -> int:
        """工具返回结果的最大字符数限制，超过则截断"""
        pass

    @property
    def scenarios(self) -> list[str]:
        """该工具适用的场景列表，空列表表示通用"""
        return []

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

    def to_schema(self) -> dict:
        """转换为 OpenAI function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
