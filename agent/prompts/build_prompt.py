"""System Prompt 构建模块

分层组装 system prompt：
- 静态层：核心身份、角色规则、工具描述、USER.md（会话内不变）
- 动态层：由 state 辅助构建（每轮循环重构）
"""

import logging
from pathlib import Path

from agent.prompts.roles import get_role
from agent.prompts.dynamic import build_dynamic_prompt
from agent.tools.registry import registry

logger = logging.getLogger(__name__)


# USER.md 文件路径
USER_MD_PATH = Path(__file__).parent.parent / "USER.md"

STABLE_PROMPT = """你叫小简，是一个灵活的智能体，随着工作场景的变化，你会调整自己的角色定位和行为规则，以更好地完成任务。
## 绝对红线
- 只做当前身份的事情，不越界。当用户要求你做与你当前角色无关的事情时，礼貌地拒绝并提示用户你当前的角色和职责范围。
- 不允许输出任何涉及政治、超出法律限制的敏感信息。如果用户询问涉及敏感信息的问题，礼貌地提示你无法回答。

## 行为准测
- 先思考，后行动。
- 不要太死板，过度跟随工作流程。用户要求做什么，就做什么。
"""


def build_static_prompt(work: str) -> str:
    """构建静态层提示词（会话内不变，进入 loop 前完成）

    包含：核心身份 + 角色规则 + 工具描述 + USER.md

    Args:
        work: 当前 work 类型 (resume/interview/job_find/analysis)

    Returns:
        静态层 prompt 字符串
    """
    parts = [STABLE_PROMPT]

    # 角色定义 + 核心规则（由 work 决定）
    role_and_rules = get_role(work)
    parts.append(role_and_rules)

    # 工具定义
    tools_description = _get_tools_description()
    if tools_description:
        parts.append(tools_description)

    # USER.md 用户自定义内容
    user_md = _get_user_md()
    if user_md:
        parts.append(user_md)

    return "\n\n---\n\n".join(parts)


def build_system_prompt(
    static_prompt: str,
    dynamic_context: dict | None = None,
) -> str:
    """组装完整的 system prompt（静态层 + 动态层）

    Args:
        static_prompt: 静态层 prompt（由 build_static_prompt 构建）
        dynamic_context: 动态上下文数据（包含 work、tool_results、stage 等）

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


def _get_user_md() -> str:
    """
    读取 USER.md 文件内容

    Returns:
        USER.md 内容，如果文件不存在则返回空字符串
    """
    try:
        if USER_MD_PATH.exists():
            content = USER_MD_PATH.read_text(encoding="utf-8")
            # 去掉注释行
            lines = [
                line for line in content.split("\n")
                if not line.strip().startswith(">")
            ]
            return "\n".join(lines).strip()
        else:
            logger.debug("USER.md 不存在，跳过加载: %s", USER_MD_PATH)
    except Exception as e:
        logger.warning("USER.md 加载失败: %s", e)
    return ""
