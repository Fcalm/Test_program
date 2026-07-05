"""OpenAI 客户端封装（支持多提供商）"""

import hashlib
import httpx
from openai import AsyncOpenAI
from backend.config import settings
from backend.provider_config import ResolvedConfig

# 客户端缓存：key = "base_url|api_key_hash"
_client_cache: dict[str, AsyncOpenAI] = {}


def _cache_key(base_url: str, api_key: str) -> str:
    """生成缓存 key（不暴露完整 key）"""
    key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
    return f"{base_url}|{key_hash}"


def create_client() -> AsyncOpenAI:
    """获取默认 OpenAI 客户端（向后兼容）"""
    return create_client_for_config(
        ResolvedConfig(
            provider="deepseek",
            base_url=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
            model=settings.LLM_MODEL,
            higher_model=settings.LLM_HIGHER_MODEL,
            context_limit=128000,
            max_tokens=None,
            scenario_configs={}
        )
    )


def create_client_for_config(config: ResolvedConfig) -> AsyncOpenAI:
    """根据解析后的配置创建或获取缓存的客户端"""
    key = _cache_key(config.base_url, config.api_key)
    if key not in _client_cache:
        _client_cache[key] = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=httpx.Timeout(60.0, connect=10.0),
            max_retries=0,  # 重试由 Agent 层控制
        )
    return _client_cache[key]


def get_model() -> str:
    """获取默认模型名称（向后兼容）"""
    return settings.LLM_MODEL