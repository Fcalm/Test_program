"""文件索引缓存服务

缓存用户的文件索引信息，加速 Agent 工具调用时的文件查询。
"""

import json
from typing import Any

from backend.services.redis_client import get_redis

# Key 前缀和 TTL
FILE_INDEX_PREFIX = "file:index:"
FILE_INDEX_TTL = 3600  # 1 小时


async def get_file_index(user_id: int) -> dict[str, Any] | None:
    """获取用户的文件索引

    Args:
        user_id: 用户 ID

    Returns:
        文件索引字典 {file_id: metadata}，不存在返回 None
    """
    redis = await get_redis()
    key = f"{FILE_INDEX_PREFIX}{user_id}"

    data = await redis.hgetall(key)
    if not data:
        return None

    return {fid: json.loads(meta) for fid, meta in data.items()}


async def set_file_index(
    user_id: int,
    files: list[dict[str, Any]],
) -> None:
    """设置用户的文件索引

    Args:
        user_id: 用户 ID
        files: 文件元数据列表
    """
    redis = await get_redis()
    key = f"{FILE_INDEX_PREFIX}{user_id}"

    # 构建 Hash 映射
    mapping = {
        str(f["id"]): json.dumps(f, ensure_ascii=False)
        for f in files
    }

    if mapping:
        await redis.delete(key)  # 清空旧索引
        await redis.hset(key, mapping=mapping)
        await redis.expire(key, FILE_INDEX_TTL)


async def get_file_meta(user_id: int, file_id: int) -> dict[str, Any] | None:
    """获取单个文件的元数据

    Args:
        user_id: 用户 ID
        file_id: 文件 ID

    Returns:
        文件元数据，不存在返回 None
    """
    redis = await get_redis()
    key = f"{FILE_INDEX_PREFIX}{user_id}"

    data = await redis.hget(key, str(file_id))
    if data:
        return json.loads(data)
    return None


async def invalidate_file_index(user_id: int) -> None:
    """使文件索引失效

    Args:
        user_id: 用户 ID
    """
    redis = await get_redis()
    await redis.delete(f"{FILE_INDEX_PREFIX}{user_id}")
