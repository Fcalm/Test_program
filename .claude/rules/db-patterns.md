# 数据库与模型规则

## SQLAlchemy 2.0 风格

所有模型必须使用 `Mapped` + `mapped_column` 声明式写法：

```python
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class Example(Base):
    __tablename__ = "examples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- **禁止**使用旧版 `Column(Integer)` 写法
- 可空字段用 `Mapped[type | None]` + `nullable=True`
- 外键用 `ForeignKey("table_name.column")`，并设 `index=True`

## JSON 列使用

项目大量使用 JSON 列存储半结构化数据（简历各段、问卷偏好）：

```python
basic_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
education: Mapped[list | None] = mapped_column(JSON, nullable=True)
```

- 读写 JSON 列时，service 层负责数据格式校验
- JSON 列变更时，同步更新：model → schema → service

## 表命名

- 表名：英文复数蛇形（`users`、`resumes`、`resume_history`）
- 外键列：`<关联表单数>_id`（如 `user_id`、`resume_id`）

## 数据库初始化

- **SQLite 单文件**（`data/app.db`）— 零配置，通过 `aiosqlite` 异步访问
- **无 Alembic** — 表在 `database.py` 的 `create_tables()` 中自动创建
- 新增表：在 `create_tables()` 中添加 `await conn.run_sync(Base.metadata.create_all)`
- 新增列：SQLite 不支持 `ALTER TABLE ADD COLUMN` 的所有场景，优先在建表时定义完整 schema

## 会话管理

```python
# database.py 提供的依赖注入
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

- Router 层通过 `db: AsyncSession = Depends(get_db)` 获取
- Service 层通过参数接收 `db`，**不得自行创建会话**
- 使用 `db.flush()` 而非 `db.commit()`（由中间件统一管理事务）

## Relationship

```python
history: Mapped[list["ResumeHistory"]] = relationship(
    back_populates="resume", cascade="all, delete-orphan"
)
```

- 级联删除用 `cascade="all, delete-orphan"`
- 双向关系必须设置 `back_populates`

## 验证方式

- 模型中使用 `Column(Integer)` 而非 `mapped_column` → 违规
- Service 中调用 `get_db()` → 违规
- 新增 JSON 列但未更新 schema → 不完整
