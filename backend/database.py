from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)
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
    """启动时建表"""
    async with engine.begin() as conn:
        from backend.models.user import User  # noqa: F401
        from backend.models.resume import Resume, ResumeHistory  # noqa: F401
        from backend.models.agent_session import AgentSession  # noqa: F401
        from backend.models.uploaded_file import UploadedFile, FileText  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
