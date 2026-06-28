"""提示词系统模块"""

from agent.prompts.build_prompt import build_static_prompt, build_system_prompt
from agent.prompts.roles import get_role, ROLES
from agent.prompts.dynamic import build_dynamic_prompt, DYNAMIC_TEMPLATES
from agent.prompts.compact import COMPACT_PROMPT

__all__ = [
    "build_static_prompt",
    "build_system_prompt",
    "get_role",
    "ROLES",
    "build_dynamic_prompt",
    "DYNAMIC_TEMPLATES",
    "COMPACT_PROMPT",
]
