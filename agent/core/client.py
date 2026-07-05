"""OpenAI 客户端封装（支持多提供商）"""

import hashlib
import httpx
from openai import AsyncOpenAI
from backend.provider_config import ResolvedConfig, load_yaml_config

# 客户端缓存：key = "base_url|api_key_hash"
_client_cache: dict[str, AsyncOpenAI] = {}


def _cache_key(base_url: str, api_key: str) -> str:
    """生成缓存 key（不暴露完整 key）"""
    key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
    return f"{base_url}|{key_hash}"


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


def create_client() -> AsyncOpenAI:
    """使用默认配置创建客户端（fallback，resolved_config 为 None 时使用）"""
    import os
    yaml_config = load_yaml_config()
    defaults = yaml_config.get("defaults", {})
    provider_key = defaults.get("provider", "deepseek")
    provider = yaml_config.get("providers", {}).get(provider_key, {})

    base_url = provider.get("base_url", "https://api.deepseek.com")
    api_key = os.getenv("OPENAI_API_KEY", "")

    return create_client_for_config(ResolvedConfig(
        provider=provider_key,
        base_url=base_url,
        api_key=api_key,
        model=defaults.get("model", ""),
        higher_model=defaults.get("higher_model", ""),
        context_limit=128000,
        max_tokens=defaults.get("max_tokens"),
    ))