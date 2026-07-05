"""Agent 会话状态缓存服务

使用 Redis 存储活跃会话状态，提供高性能读写。
"""

import json
from datetime import datetime
from typing import Any

from backend.services.redis_client import get_redis

# Key 前缀
SESSION_PREFIX = "agent:session:"
USER_SESSIONS_PREFIX = "user:sessions:"

# TTL 配置（秒）
SESSION_TTL = 86400        # 24 小时
USER_SESSIONS_TTL = 604800 # 7 天


async def save_session_state(
    session_id: str,
    user_id: int,
    state: dict,
    messages: list[dict],
    tool_cache: dict[str, Any],
    turn_count: int = 0,
) -> None:
    """保存会话状态到 Redis

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        state: AgentState 快照
        messages: 对话历史
        tool_cache: 关键数据缓存（key_data）
        turn_count: 轮次计数
    """
    redis = await get_redis()
    key = f"{SESSION_PREFIX}{session_id}"

    # 使用 Hash 存储多个字段
    await redis.hset(key, mapping={
        "state": json.dumps(state, ensure_ascii=False),
        "messages": json.dumps(messages, ensure_ascii=False),
        "tool_cache": json.dumps(tool_cache, ensure_ascii=False),
        "turn_count": str(turn_count),
        "updated_at": datetime.now().isoformat(),
    })
    await redis.expire(key, SESSION_TTL)

    # 更新用户会话列表（Sorted Set）
    user_key = f"{USER_SESSIONS_PREFIX}{user_id}"
    await redis.zadd(user_key, {session_id: datetime.now().timestamp()})
    await redis.expire(user_key, USER_SESSIONS_TTL)


async def get_session_state(session_id: str) -> dict | None:
    """从 Redis 获取会话状态

    Args:
        session_id: 会话 ID

    Returns:
        会话状态字典，不存在返回 None
    """
    redis = await get_redis()
    key = f"{SESSION_PREFIX}{session_id}"

    data = await redis.hgetall(key)
    if not data:
        return None

    return {
        "state": json.loads(data.get("state", "{}")),
        "messages": json.loads(data.get("messages", "[]")),
        "tool_cache": json.loads(data.get("tool_cache", "{}")),
        "turn_count": int(data.get("turn_count", 0)),
        "updated_at": data.get("updated_at"),
    }


async def delete_session_state(session_id: str, user_id: int) -> None:
    """删除会话状态

    Args:
        session_id: 会话 ID
        user_id: 用户 ID（用于清理用户会话列表）
    """
    redis = await get_redis()

    # 删除会话数据
    await redis.delete(f"{SESSION_PREFIX}{session_id}")

    # 从用户会话列表移除
    user_key = f"{USER_SESSIONS_PREFIX}{user_id}"
    await redis.zrem(user_key, session_id)


async def get_user_active_sessions(user_id: int, limit: int = 20) -> list[str]:
    """获取用户的活跃会话列表

    Args:
        user_id: 用户 ID
        limit: 返回数量限制

    Returns:
        会话 ID 列表（按时间倒序）
    """
    redis = await get_redis()
    user_key = f"{USER_SESSIONS_PREFIX}{user_id}"

    # 按时间倒序获取
    return await redis.zrevrange(user_key, 0, limit - 1)
