"""获取 Skill 完整指令工具

LLM 判断需要某个 Skill 时调用，返回 SKILL.md 全文。
"""

import json
import logging

from agent.tools.basetool import BaseTool
from agent.tools.registry import registry

logger = logging.getLogger(__name__)


class GetSkillPromptTool(BaseTool):
    """获取指定 Skill 的完整 SKILL.md 内容"""

    @property
    def name(self) -> str:
        return "get_skill_prompt"

    @property
    def description(self) -> str:
        return (
            "获取指定 Skill 的完整执行指令。"
            "当你需要按照特定规范（如生成简历、计算匹配度）执行任务时，"
            "先从系统提示词中找到可用的 Skill 名称，再调用此工具获取详细指令。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Skill 名称，从系统提示词的「可用 Skill」段获取",
                },
            },
            "required": ["skill_name"],
        }

    @property
    def max_results_chars(self) -> int:
        return 10000

    @property
    def scenarios(self) -> list[str]:
        return []  # 所有场景可用

    async def execute(self, skill_name: str, **kwargs) -> str:
        """获取 Skill 完整指令"""
        logger.debug("调用工具: %s, skill_name=%s", self.name, skill_name)
        from agent.skills.base import skill_registry

        skill = skill_registry.get(skill_name)
        if not skill:
            available = skill_registry.get_all_names()
            return json.dumps(
                {
                    "success": False,
                    "error": f"未找到 skill: {skill_name}",
                    "available_skills": available,
                },
                ensure_ascii=False,
            )

        full_prompt = skill.get_full_prompt()
        return json.dumps(
            {"success": True, "skill_name": skill_name, "content": full_prompt},
            ensure_ascii=False,
        )


# 注册工具
registry.register(GetSkillPromptTool)
