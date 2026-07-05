"""Compact Hook - 上下文压缩钩子

按照 harness.md 的压缩流程实现：

成功路径：新建 state + 注入压缩后消息（天然干净，无遗漏）
失败路径：compact_count +1 → 丢弃 10% → 重试 → >3 次中断

熔断器使用 state.compact_count，持久化到 DB。

记忆提炼：每两次滚动摘要更新触发一次，从滚动摘要提炼到 Memory.md。
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
MEMORY_EXTRACT_INTERVAL = 2  # 每两次滚动摘要更新触发一次记忆提炼

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


async def update_summary(state: AgentState, model: str = "deepseek-v4-flash", context_limit: int = 128000, resolved_config=None) -> None:
    """更新滚动摘要（工作笔记，不替换上下文）

    滚动摘要是当前工作的"笔记"，用于辅助压缩时快速获取上下文。
    它不会替换当前对话的完整上下文，只是作为辅助信息持续维护。

    每两次更新触发一次记忆提炼。
    """
    from agent.prompts.compact import SUMMARY_UPDATE_PROMPT
    from agent.core.client import create_client_for_config

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

    client = create_client_for_config(resolved_config)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=600,
    )

    new_summary = response.choices[0].message.content
    if new_summary:
        state.summary = new_summary
        # 更新 checkpoint 到当前累计 token
        total_tokens = state.usage.get("total_tokens", 0)
        if total_tokens == 0:
            total_tokens = count_tokens(state.messages)
        state.summary_token_checkpoint = total_tokens

        # 滚动摘要更新计数 +1
        state.summary_update_count += 1
        logger.info("滚动摘要已更新，checkpoint=%d, count=%d", state.summary_token_checkpoint, state.summary_update_count)

        # 每两次更新触发一次记忆提炼
        if state.summary_update_count % MEMORY_EXTRACT_INTERVAL == 0:
            await extract_and_save_memory(state, model, resolved_config)


async def extract_and_save_memory(state: AgentState, model: str = "deepseek-v4-flash", resolved_config=None) -> bool:
    """从滚动摘要提炼记忆并保存到 Memory.md

    Args:
        state: Agent 状态
        model: 模型名称（使用轻量模型）
        resolved_config: 配置

    Returns:
        是否有新内容被保存
    """
    from agent.prompts.compact import EXTRACT_MEMORY_PROMPT
    from agent.tools.memory import read_memory, MEMORY_MD_PATH
    from agent.core.client import create_client_for_config

    if not state.summary:
        return False

    # 读取当前 Memory.md
    current_memory = read_memory()
    if not current_memory:
        current_memory = "（空）"

    # 构建提炼 prompt
    prompt = EXTRACT_MEMORY_PROMPT.format(
        current_memory=current_memory,
        rolling_summary=state.summary,
    )

    try:
        # 使用轻量模型提炼（比主模型更快更省 token）
        client = create_client_for_config(resolved_config)
        # 使用更轻量的模型，如果没有配置则使用主模型
        extract_model = "deepseek-v4-flash"  # 轻量模型

        response = await client.chat.completions.create(
            model=extract_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=500,
        )

        result = response.choices[0].message.content
        if not result or "无新内容" in result:
            logger.info("记忆提炼：无新内容")
            return False

        # 解析提炼结果，提取条目
        new_entries = _parse_extract_result(result)
        if not new_entries:
            return False

        # 调用 memory 工具保存
        from agent.tools.memory import MemoryTool
        memory_tool = MemoryTool()
        saved_count = 0

        for category, content in new_entries:
            result_json = await memory_tool.execute(
                action="add",
                target=category,
                content=content,
            )
            result_data = json.loads(result_json)
            if result_data.get("success"):
                saved_count += 1
                logger.info("记忆提炼：已保存 [%s] %s", category, content[:50])
            else:
                logger.warning("记忆提炼保存失败: %s", result_data.get("error"))

        if saved_count > 0:
            logger.info("记忆提炼完成，保存 %d 条", saved_count)

        return saved_count > 0

    except Exception as e:
        logger.error("记忆提炼失败: %s", e)
        return False


def _parse_extract_result(result: str) -> list[tuple[str, str]]:
    """解析提炼结果，提取 (类别, 内容) 列表

    格式：[类别] 内容
    """
    entries = []
    valid_categories = {"用户偏好", "工作习惯", "项目约定", "关键教训"}

    for line in result.split("\n"):
        line = line.strip()
        if not line or line == "无新内容":
            continue

        # 尝试解析 [类别] 内容 格式
        if line.startswith("[") and "]" in line:
            bracket_end = line.index("]")
            category = line[1:bracket_end].strip()
            content = line[bracket_end + 1:].strip()

            if category in valid_categories and content:
                entries.append((category, content))

    return entries


# === CompactHook ===

class CompactHook(BaseHook):
    """上下文压缩 Hook

    按照 harness.md 流程：
    - should_trigger: 消息数 >= 6 且 token >= 75% 阈值 + 守卫检查
    - execute: 压缩循环（成功→新建state，失败→丢弃+重试→>3中断）
    - 熔断器使用 state.compact_count（持久化）

    记忆提炼：
    - 每两次滚动摘要更新触发一次
    - 会话结束（压缩前）识别一次
    """

    def __init__(
        self,
        model: str = "deepseek-v4-flash",
        context_limit: int = 128000,
        guard: CompressGuard | None = None,
        resolved_config=None,
    ) -> None:
        self._model = model
        self._context_limit = context_limit
        self._guard = guard or CompressGuard()
        self._resolved_config = resolved_config

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

        压缩前会尝试从滚动摘要提炼记忆。
        """
        logger.info("CompactHook 触发压缩")

        # 进入压缩状态（防递归）
        self._guard.enter_compress()

        try:
            # 压缩前尝试提炼记忆（最后机会）
            if state.summary:
                await extract_and_save_memory(state, self._model, self._resolved_config)

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
        from agent.core.client import create_client_for_config

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
        client = create_client_for_config(self._resolved_config)
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
        # summary_update_count 保留（累计计数，不重置）
        return AgentState(
            session_id=old_state.session_id,
            user_id=old_state.user_id,
            scenario=old_state.scenario,
            messages=recent_messages,
            key_data=key_data,
            summary=old_state.summary,
            summary_update_count=old_state.summary_update_count,
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
