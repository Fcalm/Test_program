# API 端点规范

## 路由前缀与标签

| 模块 | 前缀 | tags | 文件 |
|---|---|---|---|
| 认证 | `/auth` | `认证` | `routers/auth.py` |
| 简历 | `/resume` | `简历` | `routers/resume.py` |
| AI Agent | `/agent` | `AI Agent` | `routers/agent.py` |
| 工具（开发用） | `/tools` | `工具` | `routers/tools.py` |

- tags 用中文，与 OpenAPI 文档展示一致
- 每个 router 文件顶部 `router = APIRouter(prefix="/...", tags=[...])`

## HTTP 方法约定

| 操作 | 方法 | 示例 |
|---|---|---|
| 查询单个资源 | GET | `GET /resume` |
| 创建资源 | POST + `status_code=201` | `POST /resume` |
| 全量更新 | PUT | `PUT /resume` |
| 删除资源 | DELETE | `DELETE /resume/history/{id}` |

## 请求/响应 Schema

- 所有请求体必须有对应的 Pydantic 模型（禁止 `dict` 直接接收）
- 响应用 `response_model=XXXResponse` 显式声明
- Schema 文件按模块拆分：`schemas/user.py`、`schemas/resume.py`、`schemas/jd.py`
- 字段用 `Field(description="中文说明")` 提供文档

## 错误响应

```python
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="中文错误描述",  # 直接给前端展示
)
```

常用状态码：
- `400` — 参数错误 / 业务校验失败（如"用户名已被注册"）
- `401` — 未认证（token 缺失或过期）
- `404` — 资源不存在
- `422` — Pydantic 自动校验失败（FastAPI 默认）

## 认证端点

- 需要登录的端点：添加 `current_user: User = Depends(get_current_user)` 参数
- 公开端点（注册、登录）：不需要 `get_current_user`
- 登录返回 `{"access_token": "...", "token_type": "bearer"}`

## SSE 流式端点

```python
@router.post("/stream")
async def stream_chat(...):
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
```

- 仅 `/agent/stream` 使用 SSE
- 数据格式：`data: {json}\n\n`
- 结束标记：`data: [DONE]\n\n`

## 验证方式

- router 中直接写 `select()` / `db.execute()` → 违规，应调用 service
- 响应没有 `response_model` → 违规
- 错误消息用英文 → 违规，必须中文
