"""JD 解析工具"""

import json
import logging

from agent.tools.basetool import BaseTool
from agent.tools.registry import registry

logger = logging.getLogger(__name__)


class JDParserTool(BaseTool):
    """解析职位描述(JD)——支持文本或 URL"""

    @property
    def name(self) -> str:
        return "parse_jd_tool"

    @property
    def description(self) -> str:
        return (
            "解析职位描述(JD)，提取岗位名称、公司、职责、要求、薪资、福利等结构化信息。"
            "支持两种输入方式：直接传入 JD 文本，或传入包含 JD 的网页 URL。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "JD 原始文本"},
                "url": {"type": "string", "description": "包含 JD 内容的网页链接（如 BOSS 直聘、拉勾等招聘网站）"},
            },
        }

    @property
    def max_results_chars(self) -> int:
        return 5000

    @property
    def scenarios(self) -> list[str]:
        return ["resume", "job_find"]

    async def execute(self, text: str = "", url: str = "", **kwargs) -> str:
        """执行 JD 解析"""
        logger.debug("调用工具: %s, url=%s", self.name, url or "N/A")
        from backend.services.jd_parser import parse_jd, parse_jd_from_url
        from agent.services.agent import _format_jd_info

        if url:
            result = await parse_jd_from_url(url)
        elif text:
            result = await parse_jd(text)
        else:
            return json.dumps(
                {"success": False, "error": "请提供 JD 文本或网页链接"},
                ensure_ascii=False,
            )

        if result.success:
            data = result.data.model_dump()
            return json.dumps(
                {"success": True, "data": data, "summary": _format_jd_info(data)},
                ensure_ascii=False
            )
        return json.dumps({"success": False, "error": result.error}, ensure_ascii=False)


# 注册工具
registry.register(JDParserTool)
