"""System Prompt 构建模块

分层组装 system prompt：
- 静态层：核心身份、角色规则、工具描述、Skill 索引、Memory.md（会话内不变）
- 动态层：由 state 辅助构建（每轮循环重构）
"""

import logging
from pathlib import Path

from agent.prompts.roles import get_role
from agent.prompts.dynamic import build_dynamic_prompt
from agent.tools.registry import registry
from agent.skills.base import skill_registry

logger = logging.getLogger(__name__)


# Memory.md 文件路径（冻结快照，会话开始时读取一次）
MEMORY_MD_PATH = Path(__file__).parent.parent / "Memory.md"

STABLE_PROMPT = """你叫小简，是一个灵活的智能体，随着工作场景的变化，你会调整自己的角色定位和行为规则，以更好地完成任务。
## 绝对红线
- 只做当前身份的事情，不越界。当用户要求你做与你当前角色无关的事情时，礼貌地拒绝并提示用户你当前的角色和职责范围。
- 不允许输出任何涉及政治、超出法律限制的敏感信息。如果用户询问涉及敏感信息的问题，礼貌地提示你无法回答。

## 行为准测
- 先思考，后行动。
- 不要太死板，过度跟随工作流程。用户要求做什么，就做什么。

user_id: {user_id}
"""


def build_static_prompt(work: str, user_id: int | None = None) -> str:
    """构建静态层提示词（会话内不变，进入 loop 前完成）

    包含：核心身份 + 角色规则 + 工具描述 + Skill 索引 + Memory.md

    Args:
        work: 当前 work 类型 (resume/interview/job_find/analysis)
        user_id: 当前用户 ID

    Returns:
        静态层 prompt 字符串
    """
    parts = [STABLE_PROMPT.format(user_id=user_id or "")]

    # 角色定义 + 核心规则（由 work 决定）
    role_and_rules = get_role(work)
    parts.append(role_and_rules)

    # 工具定义
    tools_description = _get_tools_description()
    if tools_description:
        parts.append(tools_description)

    # Skill 索引
    skills_description = _get_skills_description()
    if skills_description:
        parts.append(skills_description)

    # Memory.md 持久化记忆（冻结快照）
    memory_md = _get_memory_md()
    if memory_md:
        parts.append(memory_md)

    return "\n\n---\n\n".join(parts)


def build_system_prompt(
    static_prompt: str,
    dynamic_context: dict | None = None,
) -> str:
    """组装完整的 system prompt（静态层 + 动态层）

    Args:
        static_prompt: 静态层 prompt（由 build_static_prompt 构建）
        dynamic_context: 动态上下文数据（包含 work、key_data 等）

    Returns:
        完整的 system prompt 字符串
    """
    parts = [static_prompt]

    # 动态提示词（每轮循环都可能更新）
    if dynamic_context:
        work = dynamic_context.get("work", "")
        dynamic_prompt = build_dynamic_prompt(work, dynamic_context)
        if dynamic_prompt:
            parts.append(dynamic_prompt)

    return "\n\n---\n\n".join(parts)


def _get_tools_description() -> str:
    """
    获取所有工具的描述

    Returns:
        工具描述文本
    """
    tools = registry.get_all_tools()
    if not tools:
        return ""

    lines = ["## 可用工具", ""]
    for name, tool in tools.items():
        lines.append(f"### {name}")
        lines.append(f"描述：{tool.description}")
        lines.append("")

    return "\n".join(lines)


def _get_skills_description() -> str:
    """
    获取所有 Skill 的描述索引

    Returns:
        Skill 描述文本（用于 system prompt 注入）
    """
    return skill_registry.get_all_descriptions()


def _get_memory_md() -> str:
    """读取 Memory.md 文件内容（冻结快照，会话开始时读取一次）

    Returns:
        Memory.md 内容，带使用率标头，如果文件不存在则返回空字符串
    """
    try:
        if MEMORY_MD_PATH.exists():
            content = MEMORY_MD_PATH.read_text(encoding="utf-8").strip()
            if not content:
                return ""

            # 计算使用率
            from agent.tools.memory import get_memory_usage, MEMORY_CHAR_LIMIT
            actual_chars, usage_percent = get_memory_usage(content)

            # 构建注入格式（参考 Hermes）
            header = (
                f"══════════════════════════════════════════════\n"
                f"MEMORY (持久化记忆) [{usage_percent:.0f}% — {actual_chars}/{MEMORY_CHAR_LIMIT} chars]\n"
                f"══════════════════════════════════════════════"
            )

            # 解析条目，用 § 分隔
            from agent.tools.memory import parse_memory_sections
            sections = parse_memory_sections(content)
            entries = []
            for category, items in sections.items():
                if items:
                    for item in items:
                        entries.append(f"{category}：{item}")

            if not entries:
                return ""

            body = "\n§\n".join(entries)
            return f"{header}\n{body}"
        else:
            logger.debug("Memory.md 不存在，跳过加载: %s", MEMORY_MD_PATH)
    except Exception as e:
        logger.warning("Memory.md 加载失败: %s", e)
    return ""
