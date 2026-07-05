"""文件读取工具 - 让 LLM 读取用户上传的文件内容"""

import json
import logging

from agent.tools.basetool import BaseTool
from agent.tools.registry import registry

logger = logging.getLogger(__name__)


class ReadFileTool(BaseTool):
    """读取用户上传的文件内容"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "当用户上传文件时，读取文件内容。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "description": "文件 ID"
                },
                "max_chars": {
                    "type": "integer",
                    "description": "最大返回字符数，默认 8000"
                }
            },
            "required": ["file_id"]
        }

    @property
    def max_results_chars(self) -> int:
        return 10000

    @property
    def scenarios(self) -> list[str]:
        return []  # 所有场景可用

    async def execute(self, file_id: int, max_chars: int = 8000, **kwargs) -> str:
        """执行文件读取"""
        logger.debug("调用工具: %s", self.name)
        from backend.services.file_storage import get_file_text_for_agent

        # 从 kwargs 获取 db 和 user_id（由 agent loop 注入）
        db = kwargs.get("db")
        user_id = kwargs.get("user_id")

        if not db or not user_id:
            return json.dumps(
                {"success": False, "error": "缺少数据库连接或用户信息"},
                ensure_ascii=False
            )

        text = await get_file_text_for_agent(db, file_id, user_id, max_chars)
        if text is None:
            return json.dumps(
                {"success": False, "error": f"文件不存在或无法读取 (file_id={file_id})"},
                ensure_ascii=False
            )

        return json.dumps(
            {"success": True, "file_id": file_id, "text": text, "char_count": len(text)},
            ensure_ascii=False
        )


# 注册工具
registry.register(ReadFileTool)
