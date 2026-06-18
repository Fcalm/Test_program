"""BaseAgent - Agent 核心执行引擎"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from agent.core.state import AgentState
from agent.core.client import create_client, get_model
from agent.prompts.build_prompt import build_system_prompt
from agent.tools.registry import registry
from agent.hooks.compact_hook import CompactHook

logger = logging.getLogger(__name__)

# 场景配置
SCENARIO_CONFIGS = {
    "resume": {"max_rounds": 10, "temperature": 0.4},
    "interview": {"max_rounds": 5, "temperature": 0.7},
    "job_find": {"max_rounds": 8, "temperature": 0.5},
    "analysis": {"max_rounds": 5, "temperature": 0.3},
}


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
    ):
        self.scenario = scenario
        self.user_id = user_id
        self.session_id = session_id
        self.db = db
        self.state = AgentState(
            scenario=scenario,
            user_id=user_id,
            session_id=session_id,
        )
        self._compact_hook = CompactHook(model=get_model())

    @property
    def config(self) -> dict:
        return SCENARIO_CONFIGS.get(self.scenario, SCENARIO_CONFIGS["resume"])

    @property
    def max_rounds(self) -> int:
        return self.config["max_rounds"]

    @property
    def temperature(self) -> float:
        return self.config["temperature"]

    def _build_messages(self, user_message: str) -> list[dict]:
        """构建完整的消息列表

        Args:
            user_message: 用户消息（可能已包含文件内容注入）

        Returns:
            messages 列表
        """
        # 1. 构建 system prompt
        dynamic_context = {
            "tool_results": self.state.tool_results,
            "stage": self.state.stage,
        }
        system_prompt = build_system_prompt(self.scenario, dynamic_context)

        # 2. 组装消息
        messages = [{"role": "system", "content": system_prompt}]

        # 3. 添加历史消息（排除 system）
        for msg in self.state.messages:
            if msg.get("role") != "system":
                messages.append(msg)

        # 4. 添加当前用户消息
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _call_llm(self, messages: list[dict]) -> dict:
        """调用 LLM（非流式）

        Returns:
            LLM 响应字典
        """
        client = create_client()
        model = get_model()

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
        client = create_client()
        model = get_model()

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

        stream = await client.chat.completions.create(**kwargs, stream=True)
        async for chunk in stream:
            yield chunk

    async def _handle_tool_calls(self, tool_calls: list) -> list[dict]:
        """处理工具调用

        Returns:
            工具结果消息列表
        """
        results = []
        tools = registry.get_tools_by_scenario(self.scenario)

        for tc in tool_calls:
            func_name = tc.function.name
            func_args = json.loads(tc.function.arguments)

            tool = tools.get(func_name)
            if not tool:
                result_content = json.dumps(
                    {"error": f"未知工具: {func_name}"},
                    ensure_ascii=False
                )
            else:
                try:
                    # 注入 db 和 user_id 到工具执行上下文
                    func_args["db"] = self.db
                    func_args["user_id"] = self.user_id
                    result_content = await tool.execute(**func_args)
                except Exception as e:
                    result_content = json.dumps(
                        {"error": f"工具执行失败: {str(e)}"},
                        ensure_ascii=False
                    )

            results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_content,
            })

        return results

    async def run(self, user_message: str) -> dict:
        """执行对话（非流式）

        Args:
            user_message: 用户消息

        Returns:
            {"response": str, "thinking": str, "stage": str}
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

            # 保存 assistant 消息到状态
            msg_data = {"role": "assistant", "content": content}
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
                    "stage": self.state.stage,
                }

            # 处理工具调用
            tool_results = await self._handle_tool_calls(tool_calls)
            for result in tool_results:
                self.state.messages.append(result)

            # 更新 thinking
            if content:
                thinking += content + "\n"

            # 重新构建消息（包含工具结果）
            messages = self._build_messages(user_message)

        # 超过最大轮次
        return {
            "response": content if content else "处理超时，请重试",
            "thinking": thinking,
            "stage": self.state.stage,
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
            tool_calls_data = []
            current_tool_calls = []

            async for chunk in self._call_llm_stream(messages):
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

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

            # 处理完成的工具调用
            if current_tool_calls:
                # 保存 assistant 消息
                msg_data = {"role": "assistant", "content": full_content or None}
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

                # 转换为 tool_calls 对象格式
                tool_calls_objs = []
                for tc in current_tool_calls:
                    # 创建一个简单的对象来模拟 tool_calls 结构
                    class ToolCall:
                        def __init__(self, id, function):
                            self.id = id
                            self.function = function
                    class Function:
                        def __init__(self, name, arguments):
                            self.name = name
                            self.arguments = arguments
                    tool_calls_objs.append(ToolCall(
                        id=tc["id"],
                        function=Function(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        )
                    ))

                tool_results = await self._handle_tool_calls(tool_calls_objs)
                for result in tool_results:
                    self.state.messages.append(result)

                # 重新构建消息
                messages = self._build_messages(user_message)
                continue

            # 没有工具调用，保存并返回
            self.state.add_message("assistant", full_content)
            yield {"type": "done", "data": {"response": full_content}}
            return

        # 超过最大轮次
        yield {"type": "done", "data": {"response": "处理超时，请重试"}}
