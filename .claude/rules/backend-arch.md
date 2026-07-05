# 后端分层架构规则

## 层次职责

| 层 | 目录 | 允许做的事 | 禁止做的事 |
|---|---|---|---|
| Router | `backend/routers/` | 参数校验、调用 service、组装响应 | 直接执行 SQL、写业务逻辑 |
| Service | `backend/services/` | 全部业务逻辑、调用其他 service | 直接调用 `get_db()`（DB session 由 router 传入） |
| Model | `backend/models/` | ORM 字段定义、relationship | 业务方法（保持纯数据模型） |
| Schema | `backend/schemas/` | Pydantic 字段定义、验证规则 | 业务逻辑、DB 访问 |
| Utils | `backend/utils/` | 通用工具函数（JWT、密码哈希） | 业务逻辑 |

## 依赖方向（单向，不可反向）

```
Router → Service → Model
  ↓                  ↑
Schema          (Service 读写 Model 字段)
```

- Router 可 import Schema、Service、Model（仅用于 `Depends` 类型标注）
- Service 可 import Model 和其他 Service
- **禁止**：Model import Service，Service import Router

## Router 标准写法

```python
"""<模块名> API 路由"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.utils.auth import get_current_user

router = APIRouter(prefix="/<prefix>", tags=["<中文标签>"])


@router.post("/endpoint", response_model=SomeResponse)
async def endpoint(
    req: SomeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """中文 docstring 描述接口功能"""
    result = await some_service(db, current_user.id, req)
    return result
```

## Service 标准写法

```python
"""<模块名> 业务逻辑"""

from sqlalchemy.ext.asyncio import AsyncSession


async def some_action(db: AsyncSession, user_id: int, data: dict) -> ResultType:
    """中文 docstring"""
    # 业务逻辑，db 由调用方传入
    return result
```

## 新增模块清单

新增功能模块时，按此顺序操作：

1. `backend/models/<name>.py` — ORM 模型
2. `backend/schemas/<name>.py` — 请求/响应 schema
3. `backend/services/<name>.py` — 业务逻辑
4. `backend/routers/<name>.py` — API 路由
5. `backend/main.py` — 添加 `app.include_router()`

## 验证方式

- `routers/*.py` 中出现 `await db.execute(...)` → 违规，应移到 service
- `models/*.py` 中 import `services/` → 违规，反向依赖
- `services/*.py` 中调用 `get_db()` → 违规，db session 应由调用方传入
