"""JD 解析工具"""

import json
from agent.tools.basetool import BaseTool
from agent.tools.registry import registry


class JDParserTool(BaseTool):
    """解析职位描述(JD)文本"""

    @property
    def name(self) -> str:
        return "parse_jd_tool"

    @property
    def description(self) -> str:
        return "解析职位描述(JD)文本，提取岗位名称、公司、职责、要求、薪资、福利等结构化信息。当用户提供 JD 文本时调用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "JD 原始文本"}
            },
            "required": ["text"]
        }

    @property
    def max_results_chars(self) -> int:
        return 5000

    @property
    def scenarios(self) -> list[str]:
        return ["resume", "job_find"]

    async def execute(self, text: str = "", **kwargs) -> str:
        """执行 JD 解析"""
        from backend.services.jd_parser import parse_jd
        from agent.services.agent import _format_jd_info

        result = await parse_jd(text)
        if result.success:
            data = result.data.model_dump()
            return json.dumps(
                {"success": True, "data": data, "summary": _format_jd_info(data)},
                ensure_ascii=False
            )
        return json.dumps({"success": False, "error": result.error}, ensure_ascii=False)


# 注册工具
registry.register(JDParserTool)
