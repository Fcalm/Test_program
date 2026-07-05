"""Agent 模块"""

# 导入工具以触发注册
from agent.tools import jd_parser, read_file, get_skill_prompt, database, memory

# 初始化 Skill 注册表
from agent.skills.base import skill_registry

skill_registry.scan_and_register()
