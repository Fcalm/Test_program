"""BaseAgent - Agent 核心执行引擎"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from agent.core.state import AgentState
from agent.core.client import create_client, create_client_for_config, get_model
from agent.prompts.build_prompt import build_static_prompt, build_system_prompt
from agent.tools.registry import registry
from agent.hooks.compact_hook import CompactHook, should_update_summary, update_summary
from agent.hooks.compress_guard import CompressGuard
from backend.config import settings
from backend.provider_config import ResolvedConfig

logger = logging.getLogger(__name__)


def _parse_json_lenient(raw: str) -> dict:
    """宽松解析 JSON，处理 LLM 常见的格式问题"""
    import re

    # 先尝试标准解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 尝试修复常见问题
    fixed = raw

    # 1. 移除尾部逗号（如 {"a": 1,}）
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)

    # 2. 修复缺少逗号的问题（如 "a": 1 "b": 2 -> "a": 1, "b": 2）
    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
    fixed = re.sub(r'(\d+)\s*\n\s*"', r'\1,\n"', fixed)
    fixed = re.sub(r'}\s*\n\s*"', '},\n"', fixed)
    fixed = re.sub(r']\s*\n\s*"', '],\n"', fixed)

    # 3. 尝试解析修复后的
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 4. 如果仍然失败，尝试截取到最后一个完整的 } 或 ]
    for i in range(len(raw) - 1, 0, -1):
        if raw[i] in ('}', ']'):
            try:
                return json.loads(raw[:i + 1])
            except json.JSONDecodeError:
                continue

    # 5. 最后尝试
    return json.loads(raw)


class _Ns:
    """轻量 namespace 对象，用于构建 tool_calls 兼容结构"""
    __slots__ = ("__dict__",)

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def get_scenario_configs() -> dict:
    """获取场景配置（从统一配置读取，支持运行时修改）"""
    return settings.SCENARIO_CONFIGS


# 向后兼容：模块级导出
SCENARIO_CONFIGS = get_scenario_configs()


class BaseAgent:
    """Agent 核心执行引擎

    负责：
    1. 构建 messages（system prompt + 历史 + 用户消息）
    2. 调用 LLM（支持流式/非流式）
    3. 处理 tool_calls
    4. 上下文压缩（通过 CompactHook）
    """

    def __init__(
        self,
        scenario: str = "resume",
        user_id: int | None = None,
        session_id: str = "",
        db=None,
        resolved_config: ResolvedConfig | None = None,
    ):
        self.scenario = scenario
        self.user_id = user_id
        self.session_id = session_id
        self.db = db
        self.resolved_config = resolved_config
        self.state = AgentState(
            scenario=scenario,
            user_id=user_id,
            session_id=session_id,
        )
        self._guard = CompressGuard()
        self._compact_hook = CompactHook(
            model=self.model,
            context_limit=self.context_limit,
            guard=self._guard
        )

        # 进入 loop 前构建静态 prompt（会话内不变）
        self._static_prompt = build_static_prompt(scenario, user_id)

    @property
    def max_rounds(self) -> int:
        # 硬编码场景配置
        scenario_configs = {
            "resume": {"max_rounds": 10, "temperature": 0.4},
            "interview": {"max_rounds": 5, "temperature": 0.7},
            "job_find": {"max_rounds": 8, "temperature": 0.5},
            "analysis": {"max_rounds": 5, "temperature": 0.3},
        }
        return scenario_configs.get(self.scenario, {}).get("max_rounds", 10)

    @property
    def temperature(self) -> float:
        # 硬编码场景配置
        scenario_configs = {
            "resume": {"max_rounds": 10, "temperature": 0.4},
            "interview": {"max_rounds": 5, "temperature": 0.7},
            "job_find": {"max_rounds": 8, "temperature": 0.5},
            "analysis": {"max_rounds": 5, "temperature": 0.3},
        }
        return scenario_configs.get(self.scenario, {}).get("temperature", 0.5)

    @property
    def model(self) -> str:
        if self.resolved_config:
            return self.resolved_config.model
        return get_model()

    @property
    def context_limit(self) -> int:
        if self.resolved_config:
            return self.resolved_config.context_limit
        return 128000

    def _build_messages(self, user_message: str) -> list[dict]:
        """构建完整的消息列表

        Args:
            user_message: 用户消息（可能已包含文件内容注入）

        Returns:
            messages 列表
        """
        # 1. 构建 system prompt（静态层 + 动态层）
        dynamic_context = {
            "work": self.scenario,
            "key_data": self.state.key_data,
        }
        system_prompt = build_system_prompt(self._static_prompt, dynamic_context)

        # 2. 若存在完整压缩摘要，合并到 system prompt 末尾
        compact_summary = self.state.key_data.get("_compact_summary")
        if compact_summary:
            system_prompt = f"{system_prompt}\n\n---\n\n[对话摘要]\n{compact_summary}"

        # 3. 若存在滚动摘要（工作笔记），作为辅助上下文注入（不替换完整历史）
        if self.state.summary:
            system_prompt = f"{system_prompt}\n\n---\n\n[工作笔记]\n{self.state.summary}"

        # 4. 注入用户和会话信息
        system_prompt = f"{system_prompt}\n\n---\n\n[系统信息]\nuser_id: {self.user_id}\nsession_id: {self.session_id}"

        # 5. 组装消息
        messages = [{"role": "system", "content": system_prompt}]

        # 6. 添加历史消息（排除 system）
        for msg in self.state.messages:
            if msg.get("role") != "system":
                messages.append(msg)

        # 7. 添加当前用户消息
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _call_llm(self, messages: list[dict]) -> dict:
        """调用 LLM（非流式）

        Returns:
            LLM 响应字典
        """
        if self.resolved_config:
            client = create_client_for_config(self.resolved_config)
        else:
            client = create_client()
        model = self.model

        # 获取工具 schemas
        tools_schemas = registry.get_schemas_by_scenario(self.scenario)

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools_schemas:
            kwargs["tools"] = tools_schemas
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)
        return response.choices[0]

    async def _call_llm_stream(self, messages: list[dict]) -> AsyncGenerator:
        """调用 LLM（流式）

        Yields:
            LLM 响应 chunks
        """
        if self.resolved_config:
            client = create_client_for_config(self.resolved_config)
        else:
            client = create_client()
        model = self.model

        # 获取工具 schemas
        tools_schemas = registry.get_schemas_by_scenario(self.scenario)

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "stream_options": {"include_usage": True},
        }
        if tools_schemas:
            kwargs["tools"] = tools_schemas
            kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**kwargs, stream=True)
        async for chunk in stream:
            yield chunk

    # === 工具执行：重试 + 熔断 + 截断 ===

    # 重试配置
    TOOL_MAX_RETRIES = 3
    TOOL_RETRY_DELAYS = [1, 2, 4]  # 指数退避（秒）

    async def _execute_tool(self, tool, func_args: dict) -> str:
        """执行单个工具，含重试 + 熔断 + 截断 + 守卫

        Args:
            tool: BaseTool 实例
            func_args: 工具参数（已注入 db/user_id）

        Returns:
            工具执行结果 JSON 字符串
        """
        # 注入 db 和 user_id
        func_args["db"] = self.db
        func_args["user_id"] = self.user_id

        # 进入工具执行状态（防压缩状态污染）
        self._guard.enter_tool_execution()

        try:
            last_error = None
            for attempt in range(self.TOOL_MAX_RETRIES):
                try:
                    result = await tool.execute(**func_args)

                    # 成功：重置熔断计数 + 截断
                    registry.record_success(tool.name, self.scenario)
                    print(f"{tool.name}工具调用成功")

                    # 强制截断超限输出
                    max_chars = tool.max_results_chars
                    if max_chars and len(result) > max_chars:
                        result = result[:max_chars]
                        result += json.dumps(
                            {"_truncated": f"输出超过 {max_chars} 字符，已截断"},
                            ensure_ascii=False,
                        )

                    return result

                except Exception as e:
                    last_error = e
                    logger.warning(
                        "工具 %s 执行失败 (第 %d/%d 次): %s",
                        tool.name, attempt + 1, self.TOOL_MAX_RETRIES, e,
                    )
                    if attempt < self.TOOL_MAX_RETRIES - 1:
                        await asyncio.sleep(self.TOOL_RETRY_DELAYS[attempt])

            # 重试耗尽：记录失败
            registry.record_failure(tool.name, self.scenario)
            return json.dumps(
                {"error": f"工具 {tool.name} 执行失败（已重试 {self.TOOL_MAX_RETRIES} 次）: {last_error}"},
                ensure_ascii=False,
            )
        finally:
            # 退出工具执行状态
            self._guard.exit_tool_execution()

    async def _handle_tool_calls(self, tool_calls: list) -> list[dict]:
        """处理工具调用（并发执行）

        Returns:
            工具结果消息列表（顺序与 tool_calls 一致）
        """
        tools = registry.get_tools_by_scenario(self.scenario)

        async def _run_one(tc):
            func_name = tc.function.name

            # 解析工具参数（处理 JSON 格式错误）
            try:
                func_args = _parse_json_lenient(tc.function.arguments)
            except json.JSONDecodeError as e:
                logger.warning("工具 %s 参数 JSON 解析失败: %s, 原始参数: %s", func_name, e, tc.function.arguments[:200])
                return {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(
                        {"error": f"工具参数格式错误: {str(e)}", "raw_arguments": tc.function.arguments[:500]},
                        ensure_ascii=False,
                    ),
                }

            tool = tools.get(func_name)
            if not tool:
                result_content = json.dumps(
                    {"error": f"未知工具: {func_name}"},
                    ensure_ascii=False,
                )
            else:
                result_content = await self._execute_tool(tool, func_args)

            return {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_content,
            }

        # 并发执行所有工具调用，保持顺序
        results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
        return list(results)

    async def run(self, user_message: str) -> dict:
        """执行对话（非流式）

        Args:
            user_message: 用户消息

        Returns:
            {"response": str, "thinking": str}
        """
        # 添加用户消息到状态
        self.state.add_message("user", user_message)

        # 检查是否需要压缩
        if await self._compact_hook.should_trigger(self.state):
            self.state = await self._compact_hook.execute(self.state)

        # 构建消息
        messages = self._build_messages(user_message)

        # 循环处理（最多 max_rounds 轮工具调用）
        thinking = ""
        for _ in range(self.max_rounds):
            choice = await self._call_llm(messages)

            # 提取响应
            assistant_msg = choice.message
            content = assistant_msg.content or ""
            tool_calls = assistant_msg.tool_calls

            # 提取 thinking（DeepSeek reasoning_content）
            if hasattr(assistant_msg, "reasoning_content") and assistant_msg.reasoning_content:
                thinking = assistant_msg.reasoning_content

            # 累计 token 使用
            if hasattr(choice, "usage") and choice.usage:
                self.state.usage["total_tokens"] = (
                    self.state.usage.get("total_tokens", 0) + choice.usage.total_tokens
                )

            # 保存 assistant 消息到状态（包含 thinking）
            msg_data = {"role": "assistant", "content": content}
            if thinking:
                msg_data["thinking"] = thinking
            if tool_calls:
                msg_data["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in tool_calls
                ]
            self.state.add_message(**msg_data)

            # 如果没有工具调用，返回结果
            if not tool_calls:
                return {
                    "response": content,
                    "thinking": thinking,
                    "session_id": self.session_id,
                }

            # 处理工具调用
            tool_results = await self._handle_tool_calls(tool_calls)
            for result in tool_results:
                self.state.messages.append(result)

            # 更新 thinking
            if content:
                thinking += content + "\n"

            # 检查是否需要更新滚动摘要（token 驱动）
            if should_update_summary(self.state, self.model, self.context_limit):
                await update_summary(self.state, self.model, self.context_limit)

            # 重新构建消息（包含工具结果）
            messages = self._build_messages(user_message)

        # 超过最大轮次
        return {
            "response": content if content else "处理超时，请重试",
            "thinking": thinking,
        }

    async def run_stream(self, user_message: str) -> AsyncGenerator[dict, None]:
        """执行对话（流式）

        Yields:
            {"type": "thinking"|"content"|"tool_call"|"done", "data": ...}
        """
        # 添加用户消息到状态
        self.state.add_message("user", user_message)

        # 检查是否需要压缩
        if await self._compact_hook.should_trigger(self.state):
            self.state = await self._compact_hook.execute(self.state)

        # 构建消息
        messages = self._build_messages(user_message)

        # 循环处理（最多 max_rounds 轮工具调用）
        for _ in range(self.max_rounds):
            full_content = ""
            full_thinking = ""
            tool_calls_data = []
            current_tool_calls = []

            # 进入流式响应状态
            self._guard.enter_streaming()

            try:
                async for chunk in self._call_llm_stream(messages):
                    # 累计 usage（最后一个 chunk 包含 usage 统计）
                    if hasattr(chunk, "usage") and chunk.usage:
                        self.state.usage["total_tokens"] = (
                            self.state.usage.get("total_tokens", 0) + chunk.usage.total_tokens
                        )

                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    # 处理思考过程（DeepSeek reasoning_content）
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        full_thinking += delta.reasoning_content
                        yield {"type": "thinking", "data": delta.reasoning_content}

                    # 处理内容
                    if delta.content:
                        full_content += delta.content
                        yield {"type": "content", "data": delta.content}

                    # 处理工具调用
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            # 累积工具调用数据
                            while len(current_tool_calls) <= tc.index:
                                current_tool_calls.append({
                                    "id": "",
                                    "function": {"name": "", "arguments": ""}
                                })
                            if tc.id:
                                current_tool_calls[tc.index]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    current_tool_calls[tc.index]["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    current_tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
            finally:
                # 退出流式响应状态
                self._guard.exit_streaming()

            # 处理完成的工具调用
            if current_tool_calls:
                # 保存 assistant 消息（包含 thinking）
                msg_data = {"role": "assistant", "content": full_content or None}
                if full_thinking:
                    msg_data["thinking"] = full_thinking
                msg_data["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": tc["function"],
                    }
                    for tc in current_tool_calls
                ]
                self.state.add_message(**msg_data)

                # 执行工具
                yield {"type": "tool_call", "data": current_tool_calls}

                # 转换为 tool_calls 对象格式（与 _handle_tool_calls 接口兼容）
                tool_calls_objs = [
                    _Ns(
                        id=tc["id"],
                        function=_Ns(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        ),
                    )
                    for tc in current_tool_calls
                ]

                tool_results = await self._handle_tool_calls(tool_calls_objs)
                for result in tool_results:
                    self.state.messages.append(result)

                # 检查是否需要更新滚动摘要（token 驱动）
                if should_update_summary(self.state, self.model, self.context_limit):
                    await update_summary(self.state, self.model, self.context_limit)

                # 重新构建消息
                messages = self._build_messages(user_message)
                continue

            # 没有工具调用，保存并返回
            msg_data = {"role": "assistant", "content": full_content}
            if full_thinking:
                msg_data["thinking"] = full_thinking
            self.state.add_message(**msg_data)

            # 检测面试结束标签（支持 <interviewend />、<interviewend/>、<interviewend> 等变体）
            if self.scenario == "interview" and "<interviewend" in full_content.lower():
                yield {"type": "interview_end", "data": {"session_id": self.session_id}}
                return

            # 检测轮次切换标签（支持 <round_end />、<round_end/>、<round_end> 等变体）
            if self.scenario == "interview" and "<round_end" in full_content.lower():
                yield {"type": "round_end", "data": {"session_id": self.session_id}}

            yield {"type": "done", "data": {"response": full_content, "session_id": self.session_id}}
            return

        # 超过最大轮次
        yield {"type": "done", "data": {"response": "处理超时，请重试", "session_id": self.session_id}}
