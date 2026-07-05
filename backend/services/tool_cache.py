"""工具结果缓存服务

缓存 Agent 工具调用结果，避免重复执行相同参数的工具。
"""

import hashlib
import json
from typing import Any

from backend.services.redis_client import get_redis

# Key 前缀和 TTL
TOOL_CACHE_PREFIX = "tool:cache:"
TOOL_CACHE_TTL = 1800  # 30 分钟


def _make_cache_key(
    session_id: str,
    tool_name: str,
    params: dict[str, Any],
) -> str:
    """生成缓存键（基于参数哈希）

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        params: 工具参数

    Returns:
        缓存键
    """
    params_hash = hashlib.md5(
        json.dumps(params, sort_keys=True).encode()
    ).hexdigest()[:12]
    return f"{TOOL_CACHE_PREFIX}{session_id}:{tool_name}:{params_hash}"


async def get_tool_result(
    session_id: str,
    tool_name: str,
    params: dict[str, Any],
) -> Any | None:
    """获取缓存的工具结果

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        params: 工具参数

    Returns:
        缓存的结果，不存在返回 None
    """
    redis = await get_redis()
    key = _make_cache_key(session_id, tool_name, params)

    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    return None


async def set_tool_result(
    session_id: str,
    tool_name: str,
    params: dict[str, Any],
    result: Any,
) -> None:
    """缓存工具结果

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        params: 工具参数
        result: 工具执行结果
    """
    redis = await get_redis()
    key = _make_cache_key(session_id, tool_name, params)

    await redis.setex(
        key,
        TOOL_CACHE_TTL,
        json.dumps(result, ensure_ascii=False),
    )


async def clear_session_tool_cache(session_id: str) -> None:
    """清除会话的所有工具缓存

    Args:
        session_id: 会话 ID
    """
    redis = await get_redis()
    pattern = f"{TOOL_CACHE_PREFIX}{session_id}:*"

    # 使用 SCAN 避免阻塞
    async for key in redis.scan_iter(match=pattern):
        await redis.delete(key)
