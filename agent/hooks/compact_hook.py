"""Compact Hook - 上下文压缩钩子

当 token 使用量达到阈值时，静默启动 compact agent 压缩对话历史。

压缩流程（来自 harness.md）：
1. 每次 LLM 调用后累加 usage
2. 估算下一轮 token 数 >= 75% 阈值 → 触发压缩
3. 压缩成功：组合新上下文 = system + 摘要 + 最近 3 轮，重置 usage
4. 压缩失败：丢弃最早 10% 消息 → 熔断器 +1 → 重试
5. 熔断器 > 3 → 抛出错误中断
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agent.hooks.Basehook import BaseHook

if TYPE_CHECKING:
    from agent.core.state import AgentState

logger = logging.getLogger(__name__)

# === 阈值配置 ===
COMPACT_THRESHOLD = 0.75  # 75% 触发压缩

CONTEXT_LIMITS = {
    "deepseek-v4-flash": 128_000,
    "deepseek-v4-pro": 200_000,
}


# === 熔断器 ===

class CompactCircuitBreaker:
    """压缩熔断器

    - 每次压缩失败计数 +1
    - 计数 > max_retries 时中断压缩，抛出异常
    - 压缩成功后重置计数
    """

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self.count: int = 0

    def record_failure(self) -> None:
        """记录一次压缩失败"""
        self.count += 1
        logger.warning("CompactCircuitBreaker: 失败计数 %d/%d", self.count, self.max_retries)
        if self.count > self.max_retries:
            raise CompactError(
                "上下文压缩失败次数超限，请缩短对话或重新开始会话"
            )

    def record_success(self) -> None:
        """压缩成功，重置计数"""
        self.count = 0

    def reset(self) -> None:
        """重置熔断器"""
        self.count = 0


class CompactError(Exception):
    """压缩错误"""
    pass


# === Token 计数 ===

def count_tokens(messages: list[dict], model: str = "cl100k_base") -> int:
    """估算消息列表的 token 数

    使用 tiktoken 精确计数（DeepSeek 使用与 GPT 系列兼容的 tokenizer）
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding(model)
    except ImportError:
        # tiktoken 不可用时，使用简单估算
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


def estimate_compact_tokens(messages: list[dict]) -> int:
    """估算压缩所需的空间（摘要 + 最近 3 轮）"""
    # 摘要约 300 字符 ≈ 300 tokens
    summary_tokens = 300
    # 最近 3 轮（6 条消息）
    recent = messages[-6:] if len(messages) > 6 else messages
    recent_tokens = count_tokens(recent)
    return summary_tokens + recent_tokens


# === CompactHook ===

class CompactHook(BaseHook):
    """上下文压缩 Hook

    当 token 使用量达到 75% 阈值时触发，静默启动 compact agent 压缩对话历史。

    压缩策略：
    - 新上下文 = system prompt + 压缩摘要 + 最近 3 轮原始消息
    - 压缩对用户完全透明
    """

    def __init__(self, model: str = "deepseek-v4-flash") -> None:
        self._model = model
        self._circuit_breaker = CompactCircuitBreaker()

    @property
    def name(self) -> str:
        return "compact_hook"

    async def should_trigger(self, state: AgentState) -> bool:
        """判断是否应该触发压缩

        条件：
        1. 消息数量 >= 6（至少 3 轮对话）
        2. 估算 token 数 >= 上下文限制 * 75%
        """
        if len(state.messages) < 6:
            return False

        estimated = count_tokens(state.messages)
        limit = get_context_limit(self._model)
        threshold = int(limit * COMPACT_THRESHOLD)

        logger.debug(
            "CompactHook 检查: estimated=%d, threshold=%d (%.0f%%)",
            estimated,
            threshold,
            COMPACT_THRESHOLD * 100,
        )

        return estimated >= threshold

    async def execute(self, state: AgentState) -> AgentState | None:
        """执行压缩（含失败重试逻辑）

        流程：
        1. 构建压缩请求，调用 LLM 生成摘要
        2. 成功 → 组合新上下文，重置 usage
        3. 失败 → 检查空间 → 丢弃 10% 消息 → 熔断器 +1 → 重试
        4. 熔断器 > 3 → 抛出错误
        """
        logger.info("CompactHook 触发压缩，当前 compact_count=%d", state.compact_count)

        while True:
            try:
                result = await self._try_compact(state)
                if result:
                    self._circuit_breaker.record_success()
                    return result
            except CompactError:
                raise
            except Exception as e:
                logger.error("CompactHook 压缩失败: %s", e)
                self._handle_failure(state)

    async def _try_compact(self, state: AgentState) -> AgentState | None:
        """尝试执行一次压缩"""
        from agent.prompts.compact import COMPACT_PROMPT
        from agent.core.client import create_client

        # 构建压缩请求（最多取最近 20 条）
        history_text = "\n".join(
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:200]}"
            for msg in state.messages[-20:]
        )
        prompt = COMPACT_PROMPT.format(history_messages=history_text)

        # 调用 LLM 生成摘要
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

        # 保留最近 3 轮对话（6 条消息）
        recent_messages = state.messages[-6:] if len(state.messages) > 6 else state.messages

        # 组合新上下文：摘要 + 最近 3 轮
        state.messages = [
            {"role": "system", "content": f"[对话摘要]\n{summary}"},
            *recent_messages,
        ]

        # 重置 usage
        state.usage = {}

        # 增加压缩次数
        state.increment_compact()

        logger.info(
            "CompactHook 压缩完成，compact_count=%d，消息数=%d",
            state.compact_count,
            len(state.messages),
        )

        return state

    def _handle_failure(self, state: AgentState) -> None:
        """处理压缩失败

        1. 检查：压缩所需空间 + 当前 usage > 上限？
        2. 超过上限 → 丢弃最早 10% 消息
        3. 熔断器 +1
        """
        limit = get_context_limit(self._model)
        current_tokens = count_tokens(state.messages)
        compact_tokens = estimate_compact_tokens(state.messages)

        if current_tokens + compact_tokens > limit:
            # 空间不足，丢弃最早 10% 消息
            discard_count = max(1, len(state.messages) // 10)
            state.messages = state.messages[discard_count:]
            logger.warning(
                "CompactHook 空间不足，丢弃 %d 条消息，剩余 %d 条",
                discard_count,
                len(state.messages),
            )

        self._circuit_breaker.record_failure()
