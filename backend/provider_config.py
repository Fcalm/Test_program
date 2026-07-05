"""多 LLM 提供商配置管理

层级：
1. config.yaml → 服务商模板 + 全局默认
2. user_settings 表 → 用户个性化配置
3. 代码硬编码 → 最终兜底

优先级：用户配置 > YAML 默认 > 硬编码默认
"""

from __future__ import annotations

import os
import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

import yaml
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.user_settings import UserSettings
from backend.utils.crypto import decrypt_api_key

# 路径
_YAML_PATH = Path(__file__).parent.parent / "config.yaml"


@dataclass
class ModelInfo:
    id: str
    context_limit: int = 128_000
    description: str = ""


@dataclass
class ProviderInfo:
    key: str              # "deepseek", "mimo", "local"
    name: str             # 显示名
    base_url: str
    models: list[ModelInfo] = field(default_factory=list)
    default_model: str = ""
    requires_api_key: bool = True


@dataclass
class ResolvedConfig:
    """解析后的最终配置（用于 LLM 调用）"""
    provider: str
    base_url: str
    api_key: str
    model: str
    higher_model: str
    context_limit: int
    max_tokens: int | None
    scenario_configs: dict


@lru_cache()
def load_yaml_config() -> dict:
    """加载并缓存 config.yaml"""
    if not _YAML_PATH.exists():
        return {}
    with open(_YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_all_providers() -> list[ProviderInfo]:
    """返回所有服务商信息（给前端用）"""
    yaml_config = load_yaml_config()
    providers_data = yaml_config.get("providers", {})

    providers = []
    for key, data in providers_data.items():
        models = [
            ModelInfo(
                id=m["id"],
                context_limit=m.get("context_limit", 128000),
                description=m.get("description", "")
            )
            for m in data.get("models", [])
        ]
        providers.append(ProviderInfo(
            key=key,
            name=data.get("name", key),
            base_url=data.get("base_url", ""),
            models=models,
            default_model=data.get("default_model", ""),
            requires_api_key=data.get("requires_api_key", True)
        ))

    return providers


def get_provider(key: str) -> ProviderInfo | None:
    """获取单个服务商信息"""
    providers = get_all_providers()
    for p in providers:
        if p.key == key:
            return p
    return None


def _get_model_context_limit(provider: ProviderInfo, model_id: str) -> int:
    """从 provider 的 models 列表中查找模型的 context_limit"""
    for m in provider.models:
        if m.id == model_id:
            return m.context_limit
    return 128_000  # 默认值


async def resolve_config(user_id: int | None, db: AsyncSession | None = None) -> ResolvedConfig:
    """核心解析函数，合并三层配置

    优先级：用户 user_settings > config.yaml defaults > 代码硬编码默认值
    """
    yaml_config = load_yaml_config()
    defaults = yaml_config.get("defaults", {})
    providers_data = yaml_config.get("providers", {})

    # 默认值
    provider_key = defaults.get("provider", "deepseek")
    model = defaults.get("model", "")
    higher_model = defaults.get("higher_model", "")
    max_tokens = defaults.get("max_tokens")
    scenario_configs = defaults.get("scenario_configs", {})

    # 尝试从用户配置覆盖
    user_api_key = None
    if user_id and db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        user_settings = result.scalar_one_or_none()

        if user_settings:
            if user_settings.provider:
                provider_key = user_settings.provider
            if user_settings.model:
                model = user_settings.model
            if user_settings.higher_model:
                higher_model = user_settings.higher_model
            if user_settings.api_key:
                user_api_key = decrypt_api_key(user_settings.api_key)
            if user_settings.scenario_overrides:
                try:
                    overrides = json.loads(user_settings.scenario_overrides)
                    if overrides:
                        scenario_configs = {**scenario_configs, **overrides}
                except json.JSONDecodeError:
                    pass

    # 获取 provider 信息
    provider_data = providers_data.get(provider_key, {})
    provider = ProviderInfo(
        key=provider_key,
        name=provider_data.get("name", provider_key),
        base_url=provider_data.get("base_url", ""),
        models=[],
        default_model=provider_data.get("default_model", ""),
        requires_api_key=provider_data.get("requires_api_key", True)
    )

    # 如果用户没选模型，使用 provider 的默认模型
    if not model:
        model = provider.default_model

    # 确定 API Key（优先级：用户配置 > 环境变量 > 空）
    api_key = user_api_key or ""

    # 计算 context_limit
    context_limit = _get_model_context_limit(provider, model)

    return ResolvedConfig(
        provider=provider_key,
        base_url=provider.base_url,
        api_key=api_key,
        model=model,
        higher_model=higher_model,
        context_limit=context_limit,
        max_tokens=max_tokens,
        scenario_configs=scenario_configs
    )


def save_yaml_config(config: dict) -> None:
    """保存配置到 config.yaml"""
    with open(_YAML_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    # 清除缓存，下次加载时获取最新配置
    load_yaml_config.cache_clear()


def update_defaults_in_yaml(updates: dict) -> None:
    """更新 config.yaml 中的 defaults 部分"""
    yaml_config = load_yaml_config()
    if "defaults" not in yaml_config:
        yaml_config["defaults"] = {}
    yaml_config["defaults"].update(updates)
    save_yaml_config(yaml_config)