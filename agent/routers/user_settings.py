"""用户 LLM 配置 API"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from backend.database import get_db
from backend.models.user import User
from backend.models.user_settings import UserSettings
from backend.utils.auth import get_current_user
from backend.provider_config import get_all_providers, resolve_config
from backend.utils.crypto import encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/agent", tags=["用户配置"])


class UserSettingsResponse(BaseModel):
    provider: str
    api_key_set: bool  # 是否已设置 API Key（不暴露实际值）
    model: str
    higher_model: str
    scenario_overrides: dict


class UserSettingsUpdateRequest(BaseModel):
    provider: str | None = None
    api_key: str | None = None  # 空字符串表示清除
    model: str | None = None
    higher_model: str | None = None
    scenario_overrides: dict | None = None


class ProviderInfoResponse(BaseModel):
    key: str
    name: str
    base_url: str
    models: list[dict]
    default_model: str
    requires_api_key: bool


@router.get("/user-settings", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的 LLM 配置"""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        # 返回默认配置
        from backend.provider_config import load_yaml_config
        yaml_config = load_yaml_config()
        defaults = yaml_config.get("defaults", {})
        return UserSettingsResponse(
            provider=defaults.get("provider", "deepseek"),
            api_key_set=False,
            model=defaults.get("model", ""),
            higher_model=defaults.get("higher_model", ""),
            scenario_overrides={}
        )

    return UserSettingsResponse(
        provider=user_settings.provider,
        api_key_set=bool(user_settings.api_key),
        model=user_settings.model,
        higher_model=user_settings.higher_model,
        scenario_overrides=_parse_json(user_settings.scenario_overrides)
    )


@router.put("/user-settings", response_model=UserSettingsResponse)
async def update_user_settings(
    req: UserSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户的 LLM 配置"""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        # 创建新记录
        user_settings = UserSettings(user_id=current_user.id)
        db.add(user_settings)

    # 更新字段
    if req.provider is not None:
        user_settings.provider = req.provider

    if req.api_key is not None:
        if req.api_key == "":
            user_settings.api_key = None
        else:
            user_settings.api_key = encrypt_api_key(req.api_key)

    if req.model is not None:
        user_settings.model = req.model

    if req.higher_model is not None:
        user_settings.higher_model = req.higher_model

    if req.scenario_overrides is not None:
        import json
        user_settings.scenario_overrides = json.dumps(req.scenario_overrides, ensure_ascii=False)

    await db.flush()

    return UserSettingsResponse(
        provider=user_settings.provider,
        api_key_set=bool(user_settings.api_key),
        model=user_settings.model,
        higher_model=user_settings.higher_model,
        scenario_overrides=_parse_json(user_settings.scenario_overrides)
    )


@router.get("/providers", response_model=list[ProviderInfoResponse])
async def get_providers():
    """获取所有可用的服务商及其模型列表"""
    providers = get_all_providers()
    return [
        ProviderInfoResponse(
            key=p.key,
            name=p.name,
            base_url=p.base_url,
            models=[{"id": m.id, "context_limit": m.context_limit, "description": m.description} for m in p.models],
            default_model=p.default_model,
            requires_api_key=p.requires_api_key
        )
        for p in providers
    ]


def _parse_json(json_str: str) -> dict:
    """解析 JSON 字符串，失败返回空字典"""
    import json
    try:
        return json.loads(json_str) if json_str else {}
    except (json.JSONDecodeError, TypeError):
        return {}