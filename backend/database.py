from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings, DATA_DIR

# 确保 data 目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"timeout": 30},  # SQLite 锁等待 30 秒（默认 5 秒太短）
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """SQLite 连接初始化：启用 WAL 模式 + 外键约束"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 秒，与 connect_args.timeout 一致
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    """启动时建表（SQLite，按模型定义直接创建）"""
    async with engine.begin() as conn:
        from backend.models.user import User  # noqa: F401
        from backend.models.resume import Resume, ResumeHistory  # noqa: F401
        from backend.models.agent_session import AgentSession  # noqa: F401
        from backend.models.uploaded_file import UploadedFile  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

        # 增量迁移：为已有表添加新列（SQLite ALTER TABLE ADD COLUMN）
        await _run_migrations(conn)


async def _run_migrations(conn):
    """增量迁移：为已有表添加新列

    SQLite 支持 ALTER TABLE ADD COLUMN（带 DEFAULT 的 nullable 列）。
    使用 try/except 忽略"column already exists"错误，保证幂等。
    """
    migrations = [
        "ALTER TABLE agent_sessions ADD COLUMN uploaded_file_ids TEXT DEFAULT '[]'",
        "ALTER TABLE resume_history ADD COLUMN name VARCHAR(100)",
    ]
    for sql in migrations:
        try:
            await conn.execute(text(sql))
        except Exception:
            # 列已存在，忽略
            pass
