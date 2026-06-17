"""Compact Hook - 上下文压缩钩子

当 token 使用量达到阈值时，静默启动 compact agent 压缩对话历史。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent.hooks.Basehook import BaseHook

if TYPE_CHECKING:
    from agent.core.state import AgentState

logger = logging.getLogger(__name__)

# 阈值配置
COMPACT_THRESHOLD = 0.75  # 75% 触发压缩
CONTEXT_LIMITS = {
    "deepseek-v4-flash": 128_000,
    "deepseek-v4-pro": 128_000,
}


def estimate_tokens(state: AgentState) -> int:
    """估算当前消息的 token 数量

    使用简单估算：中文约 1.5 token/字，英文约 0.25 token/word
    """
    total_chars = 0
    for msg in state.messages:
        content = msg.get("content", "")
        if content:
            total_chars += len(content)
    # 简单估算：平均每个字符约 1 token
    return total_chars


def get_context_limit(model: str) -> int:
    """获取模型的上下文窗口限制"""
    return CONTEXT_LIMITS.get(model, 128_000)


class CompactHook(BaseHook):
    """上下文压缩 Hook

    当 token 使用量达到 75% 阈值时触发，静默启动 compact agent 压缩对话历史。
    """

    def __init__(self, model: str = "deepseek-v4-flash") -> None:
        self._model = model

    @property
    def name(self) -> str:
        return "compact_hook"

    async def should_trigger(self, state: AgentState) -> bool:
        """判断是否应该触发压缩

        条件：
        1. 估算 token 数 >= 上下文限制 * 75%
        2. 消息数量 >= 6（至少 3 轮对话）
        """
        if len(state.messages) < 6:
            return False

        estimated = estimate_tokens(state)
        limit = get_context_limit(self._model)
        threshold = limit * COMPACT_THRESHOLD

        logger.debug(
            "CompactHook 检查: estimated=%d, threshold=%d (%.0f%%)",
            estimated,
            threshold,
            COMPACT_THRESHOLD * 100,
        )

        return estimated >= threshold

    async def execute(self, state: AgentState) -> AgentState | None:
        """执行压缩

        1. 构建 compact 请求
        2. 调用 LLM 生成摘要
        3. 替换消息历史为摘要 + 最近 3 轮
        4. 增加 compact_count
        """
        from agent.prompts.compact import COMPACT_PROMPT
        from agent.core.client import create_client

        logger.info("CompactHook 触发压缩，当前 compact_count=%d", state.compact_count)

        # 构建压缩请求
        history_text = "\n".join(
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:100]}"
            for msg in state.messages[-20:]  # 最多取最近 20 条
        )
        prompt = COMPACT_PROMPT.format(history_messages=history_text)

        # 调用 LLM 生成摘要
        client = create_client()
        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            summary = response.choices[0].message.content
        except Exception as e:
            logger.error("CompactHook LLM 调用失败: %s", e)
            return None

        if not summary:
            logger.warning("CompactHook LLM 返回空摘要")
            return None

        # 保留最近 3 轮对话（6 条消息）
        recent_messages = state.messages[-6:] if len(state.messages) > 6 else state.messages

        # 替换消息历史：摘要 + 最近 3 轮
        state.messages = [
            {"role": "system", "content": f"[对话摘要]\n{summary}"},
            *recent_messages,
        ]

        # 增加压缩次数
        state.increment_compact()

        logger.info(
            "CompactHook 压缩完成，新 compact_count=%d，消息数=%d",
            state.compact_count,
            len(state.messages),
        )

        return state
