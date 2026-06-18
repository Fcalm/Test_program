"""Agent 对话入口 - 基于 BaseAgent 的流式/非流式实现

本模块是对 BaseAgent 的薄封装，提供与路由层兼容的函数签名。
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.baseagent import BaseAgent, SCENARIO_CONFIGS
from agent.core.state import AgentState


async def chat_with_agent(
    message: str,
    state: AgentState,
    db: AsyncSession | None = None,
) -> dict:
    """
    与 Agent 对话（非流式）

    Args:
        message: 用户消息
        state: 当前对话状态（已从 DB 加载或新建）
        db: 数据库会话（用于工具调用）

    Returns:
        {"response": str, "thinking": str, "stage": str}
    """
    agent = BaseAgent(
        scenario=state.scenario,
        user_id=state.user_id,
        session_id=state.session_id,
        db=db,
    )
    # 恢复已有状态（包含历史消息、工具结果等）
    agent.state = state

    return await agent.run(message)


async def chat_with_agent_stream(
    message: str,
    state: AgentState,
    db: AsyncSession | None = None,
) -> AsyncGenerator[dict, None]:
    """
    与 Agent 对话（流式输出）

    Args:
        message: 用户消息
        state: 当前对话状态（已从 DB 加载或新建）
        db: 数据库会话（用于工具调用）

    Yields:
        {"type": "thinking"|"content"|"tool_call"|"done", "data": ...}
    """
    agent = BaseAgent(
        scenario=state.scenario,
        user_id=state.user_id,
        session_id=state.session_id,
        db=db,
    )
    # 恢复已有状态
    agent.state = state

    async for chunk in agent.run_stream(message):
        yield chunk
