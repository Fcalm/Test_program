"""统一配置管理

所有配置从 .env 加载，运行时可通过 API 修改内存中的值并写回 .env。
敏感字段（SECRET_KEY、OPENAI_API_KEY）不暴露给前端。
"""

import json
from pathlib import Path

from pydantic_settings import BaseSettings


# .env 文件路径
_ENV_PATH = Path(__file__).parent.parent / ".env"

# 数据目录
DATA_DIR = Path(__file__).parent.parent / "data"

# 前端可配置字段（非敏感）
EXPOSABLE_FIELDS = {
    "DEBUG", "LOG_LEVEL",
}

# 敏感字段（前端不可见、PUT 不可修改）
_SENSITIVE_FIELDS = {"SECRET_KEY", "OPENAI_API_KEY"}


class Settings(BaseSettings):
    # === JWT ===
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # === Redis ===
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20

    # === 系统 ===
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    @property
    def DATABASE_URL(self) -> str:
        db_path = DATA_DIR / "app.db"
        return f"sqlite+aiosqlite:///{db_path.as_posix()}"

    class Config:
        env_file = str(_ENV_PATH)
        env_file_encoding = "utf-8"


def _env_value(value) -> str:
    """将配置值序列化为 .env 兼容的字符串

    dict/list → JSON；其他 → str()
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def save_to_env(updates: dict) -> None:
    """将配置变更写回 .env 文件

    读取现有 .env → 更新对应 key → 写回。敏感字段被过滤。
    """
    # 过滤敏感字段
    safe_updates = {k: v for k, v in updates.items() if k not in _SENSITIVE_FIELDS}
    if not safe_updates:
        return

    # 读取现有 .env
    lines: list[str] = []
    existing_keys: set[str] = set()
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)

    # 构建 key → line 映射
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in safe_updates:
                new_lines.append(f"{key}={_env_value(safe_updates[key])}\n")
                existing_keys.add(key)
                continue
        new_lines.append(line)

    # 追加不存在的 key
    for key, value in safe_updates.items():
        if key not in existing_keys:
            new_lines.append(f"{key}={_env_value(value)}\n")

    _ENV_PATH.write_text("".join(new_lines), encoding="utf-8")


settings = Settings()
