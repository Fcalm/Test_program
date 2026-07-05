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
from agent.hooks.compress_guard import CompressGuard

if TYPE_CHECKING:
    from agent.core.state import AgentState

logger = logging.getLogger(__name__)

# === 阈值配置 ===
COMPACT_THRESHOLD = 0.75  # 75% 触发完整压缩
COMPACT_MAX_RETRIES = 3   # 熔断器上限
SUMMARY_TOKEN_RATIO = 0.10  # 每消耗 10% 上下文窗口更新一次滚动摘要

CONTEXT_LIMITS = {
    "deepseek-v4-flash": 128_000,
    "deepseek-v4-pro": 200_000,
}


# === 错误 ===

class CompactError(Exception):
    """压缩错误（熔断器中断时抛出）"""
    pass


# === Token 计数 ===

# 缓存：(id(messages), len(messages)) → token count
_token_cache: dict[tuple, int] = {}


def count_tokens(messages: list[dict], model: str = "cl100k_base") -> int:
    """估算消息列表的 token 数（tiktoken 精确计数，失败降级为字符估算）

    基于消息列表 id 和长度做缓存，避免每轮重复 encode。
    """
    cache_key = (id(messages), len(messages))
    cached = _token_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import tiktoken
        enc = tiktoken.get_encoding(model)
    except Exception:
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        _token_cache[cache_key] = total_chars
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

    _token_cache[cache_key] = total
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


# === 滚动摘要 ===

def get_token_checkpoint_interval(model: str, context_limit: int = 128000) -> int:
    """获取滚动摘要更新的 token 间隔（上下文窗口的 10%）"""
    return int(context_limit * SUMMARY_TOKEN_RATIO)


def should_update_summary(state: AgentState, model: str = "deepseek-v4-flash", context_limit: int = 128000) -> bool:
    """判断是否需要更新滚动摘要

    条件：累计 token 数达到下一个 10% 检查点
    """
    interval = get_token_checkpoint_interval(model, context_limit)
    # 当前累计 token（从 usage 中取 total_tokens，若无则估算）
    total_tokens = state.usage.get("total_tokens", 0)
    if total_tokens == 0:
        total_tokens = count_tokens(state.messages)

    next_checkpoint = state.summary_token_checkpoint + interval
    return total_tokens >= next_checkpoint


async def update_summary(state: AgentState, model: str = "deepseek-v4-flash", context_limit: int = 128000) -> None:
    """更新滚动摘要（工作笔记，不替换上下文）

    滚动摘要是当前工作的"笔记"，用于辅助压缩时快速获取上下文。
    它不会替换当前对话的完整上下文，只是作为辅助信息持续维护。
    """
    from agent.prompts.compact import SUMMARY_UPDATE_PROMPT
    from agent.core.client import create_client

    # 取最近 N 条消息作为更新依据
    recent = state.messages[-12:] if len(state.messages) > 12 else state.messages
    recent_text = "\n".join(
        f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:300]}"
        for msg in recent
        if msg.get("content")
    )

    prompt = SUMMARY_UPDATE_PROMPT.format(
        场景=state.scenario or "未知",
        current_summary=state.summary or "（无）",
        recent_messages=recent_text,
    )

    client = create_client()
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=400,
    )

    new_summary = response.choices[0].message.content
    if new_summary:
        state.summary = new_summary
        # 更新 checkpoint 到当前累计 token
        total_tokens = state.usage.get("total_tokens", 0)
        if total_tokens == 0:
            total_tokens = count_tokens(state.messages)
        state.summary_token_checkpoint = total_tokens
        logger.info("滚动摘要已更新，checkpoint=%d", state.summary_token_checkpoint)


# === CompactHook ===

class CompactHook(BaseHook):
    """上下文压缩 Hook

    按照 harness.md 流程：
    - should_trigger: 消息数 >= 6 且 token >= 75% 阈值 + 守卫检查
    - execute: 压缩循环（成功→新建state，失败→丢弃+重试→>3中断）
    - 熔断器使用 state.compact_count（持久化）
    """

    def __init__(
        self,
        model: str = "deepseek-v4-flash",
        context_limit: int = 128000,
        guard: CompressGuard | None = None
    ) -> None:
        self._model = model
        self._context_limit = context_limit
        self._guard = guard or CompressGuard()

    @property
    def name(self) -> str:
        return "compact_hook"

    async def should_trigger(self, state: AgentState) -> bool:
        """判断是否应该触发压缩

        条件：消息数 >= 6 且 token >= 上下文限制 * 75% 且守卫允许
        优先使用 LLM 响应回读的 total_tokens，避免重复 tiktoken 计数。
        """
        # 守卫检查：压缩中 / 工具执行中 / 流式响应中 不触发
        if not self._guard.can_compress():
            logger.debug("CompactHook 守卫阻止压缩: %s", self._guard)
            return False

        if len(state.messages) < 6:
            return False

        # 优先用 API 回读的 token 数（每轮 LLM 调用后已累加）
        estimated = state.usage.get("total_tokens", 0)
        if estimated == 0:
            estimated = count_tokens(state.messages)
        limit = self._context_limit
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

        # 进入压缩状态（防递归）
        self._guard.enter_compress()

        try:
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
        finally:
            # 退出压缩状态
            self._guard.exit_compress()

    async def _call_llm_compact(self, state: AgentState) -> str:
        """调用 LLM 生成压缩摘要

        将提示词、滚动摘要（工作笔记）、完整消息发给 LLM 进行压缩。
        滚动摘要作为辅助上下文，帮助 LLM 更好地理解对话脉络，但不替代完整历史。
        """
        from agent.prompts.compact import COMPACT_PROMPT, ROLLING_SUMMARY_SECTION
        from agent.core.client import create_client

        # 构建滚动摘要辅助段落
        rolling_section = ""
        if state.summary:
            rolling_section = ROLLING_SUMMARY_SECTION.format(rolling_summary=state.summary)

        # 组装压缩请求（最多取最近 20 条）
        history_text = "\n".join(
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:200]}"
            for msg in state.messages[-20:]
        )
        prompt = COMPACT_PROMPT.format(
            rolling_summary_section=rolling_section,
            history_messages=history_text,
        )

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

        保留：session_id, user_id, scenario, key_data, summary（滚动摘要）
        重建：messages, usage

        摘要注入方式：存入 key_data["_compact_summary"]，
        由 _build_messages 合并到 system prompt。
        """
        from agent.core.state import AgentState

        # 保留最近 3 轮对话（6 条消息），过滤掉 system 消息
        raw_recent = old_state.messages[-6:] if len(old_state.messages) > 6 else old_state.messages
        recent_messages = [m for m in raw_recent if m.get("role") != "system"]

        # 将压缩摘要存入 key_data，由 _build_messages 合并到 system prompt
        key_data = dict(old_state.key_data)
        key_data["_compact_summary"] = summary

        # 新建 state（天然干净，无遗漏）
        # 滚动摘要保留，checkpoint 归零（压缩后重新开始计数）
        return AgentState(
            session_id=old_state.session_id,
            user_id=old_state.user_id,
            scenario=old_state.scenario,
            messages=recent_messages,
            key_data=key_data,
            summary=old_state.summary,
            # summary_token_checkpoint 归 0：压缩后重新开始计数
            # compact_count 归 0：压缩成功重置熔断器
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
        limit = self._context_limit
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
