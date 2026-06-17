"""Compact Hook - 上下文压缩钩子

按照 harness.md 的压缩流程实现：

成功路径：新建 state + 注入压缩后消息（天然干净，无遗漏）
失败路径：compact_count +1 → 丢弃 10% → 重试 → >3 次中断

熔断器使用 state.compact_count，持久化到 DB。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from agent.hooks.Basehook import BaseHook

if TYPE_CHECKING:
    from agent.core.state import AgentState

logger = logging.getLogger(__name__)

# === 阈值配置 ===
COMPACT_THRESHOLD = 0.75  # 75% 触发压缩
COMPACT_MAX_RETRIES = 3   # 熔断器上限

CONTEXT_LIMITS = {
    "deepseek-v4-flash": 128_000,
    "deepseek-v4-pro": 200_000,
}


# === 错误 ===

class CompactError(Exception):
    """压缩错误（熔断器中断时抛出）"""
    pass


# === Token 计数 ===

def count_tokens(messages: list[dict], model: str = "cl100k_base") -> int:
    """估算消息列表的 token 数（tiktoken 精确计数）"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding(model)
    except ImportError:
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        return total_chars

    total = 0
    for msg in messages:
        total += 4  # 每条消息固定开销（role、分隔符）
        content = msg.get("content")
        if isinstance(content, str):
            total += len(enc.encode(content))
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                total += len(enc.encode(json.dumps(tc, ensure_ascii=False)))
        if msg.get("role") == "tool":
            total += len(enc.encode(msg.get("content", "")))
    return total


def get_context_limit(model: str) -> int:
    """获取模型的上下文窗口限制"""
    return CONTEXT_LIMITS.get(model, 128_000)


def estimate_compact_space(messages: list[dict]) -> int:
    """估算压缩所需空间（摘要 + 最近 3 轮）"""
    summary_tokens = 300
    recent = messages[-6:] if len(messages) > 6 else messages
    recent_tokens = count_tokens(recent)
    return summary_tokens + recent_tokens


# === CompactHook ===

class CompactHook(BaseHook):
    """上下文压缩 Hook

    按照 harness.md 流程：
    - should_trigger: 消息数 >= 6 且 token >= 75% 阈值
    - execute: 压缩循环（成功→新建state，失败→丢弃+重试→>3中断）
    - 熔断器使用 state.compact_count（持久化）
    """

    def __init__(self, model: str = "deepseek-v4-flash") -> None:
        self._model = model

    @property
    def name(self) -> str:
        return "compact_hook"

    async def should_trigger(self, state: AgentState) -> bool:
        """判断是否应该触发压缩

        条件：消息数 >= 6 且 token >= 上下文限制 * 75%
        """
        if len(state.messages) < 6:
            return False

        estimated = count_tokens(state.messages)
        limit = get_context_limit(self._model)
        threshold = int(limit * COMPACT_THRESHOLD)

        logger.debug(
            "CompactHook 检查: estimated=%d, threshold=%d (%.0f%%)",
            estimated, threshold, COMPACT_THRESHOLD * 100,
        )

        return estimated >= threshold

    async def execute(self, state: AgentState) -> AgentState:
        """执行压缩循环

        成功：新建 state + 注入压缩消息 → 返回新 state
        失败：compact_count +1 → 丢弃 10% → 重试 → >3 次抛出 CompactError
        """
        logger.info("CompactHook 触发压缩")

        while True:
            try:
                # Step 1 + 2: 调用 LLM 压缩
                summary = await self._call_llm_compact(state)

                # Step 3a: 成功 → 新建 state
                new_state = self._create_compacted_state(state, summary)
                logger.info("CompactHook 压缩成功，新消息数=%d", len(new_state.messages))
                return new_state

            except CompactError:
                raise

            except Exception as e:
                # Step 3b: 失败处理
                logger.error("CompactHook 压缩失败: %s", e)
                self._handle_failure(state)

    async def _call_llm_compact(self, state: AgentState) -> str:
        """调用 LLM 生成压缩摘要"""
        from agent.prompts.compact import COMPACT_PROMPT
        from agent.core.client import create_client

        # 组装压缩请求（最多取最近 20 条）
        history_text = "\n".join(
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:200]}"
            for msg in state.messages[-20:]
        )
        prompt = COMPACT_PROMPT.format(history_messages=history_text)

        # 调用 LLM
        client = create_client()
        response = await client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )

        summary = response.choices[0].message.content
        if not summary:
            raise ValueError("LLM 返回空摘要")

        return summary

    def _create_compacted_state(self, old_state: AgentState, summary: str) -> AgentState:
        """新建 state + 注入压缩后的消息

        保留：session_id, user_id, scenario, tool_results
        重建：messages, usage, turn_count, compact_count（保留原值）
        """
        from agent.core.state import AgentState

        # 保留最近 3 轮对话（6 条消息）
        recent_messages = old_state.messages[-6:] if len(old_state.messages) > 6 else old_state.messages

        # 组合压缩后消息
        compacted_messages = [
            {"role": "system", "content": f"[对话摘要]\n{summary}"},
            *recent_messages,
        ]

        # 新建 state（天然干净，无遗漏）
        return AgentState(
            session_id=old_state.session_id,
            user_id=old_state.user_id,
            scenario=old_state.scenario,
            stage=old_state.stage,
            messages=compacted_messages,
            tool_results=old_state.tool_results,  # 保留已解析的 JD/简历
            compact_count=old_state.compact_count,  # 保留熔断器计数
        )

    def _handle_failure(self, state: AgentState) -> None:
        """处理压缩失败

        1. compact_count +1（可能抛出 CompactError）
        2. 检查空间
        3. 丢弃最早 10% 消息（如果空间不足）
        """
        # 熔断器：compact_count +1，超过上限抛出异常
        state.increment_compact()
        if state.compact_count > COMPACT_MAX_RETRIES:
            raise CompactError(
                "上下文压缩失败次数超限，请缩短对话或重新开始会话"
            )

        # 检查空间
        limit = get_context_limit(self._model)
        current_tokens = count_tokens(state.messages)
        compact_space = estimate_compact_space(state.messages)

        if current_tokens + compact_space > limit:
            # 空间不足，丢弃最早 10% 消息
            discard_count = max(1, len(state.messages) // 10)
            state.messages = state.messages[discard_count:]
            logger.warning(
                "CompactHook 空间不足，丢弃 %d 条消息，剩余 %d 条",
                discard_count, len(state.messages),
            )
