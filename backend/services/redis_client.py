"""Redis 客户端封装

提供连接池管理和统一的 Redis 访问接口。
"""

import redis.asyncio as redis

from backend.config import settings

# Redis 连接池（延迟初始化）
redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """获取 Redis 连接

    使用延迟初始化，首次调用时创建连接池。
    """
    global redis_pool
    if redis_pool is None:
        redis_pool = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
    return redis_pool


async def close_redis():
    """关闭 Redis 连接

    在应用关闭时调用，释放连接池资源。
    """
    global redis_pool
    if redis_pool:
        await redis_pool.close()
        redis_pool = None
