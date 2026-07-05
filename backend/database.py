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
    """启动时建表 + 增量迁移"""
    async with engine.begin() as conn:
        # 先执行需要在 create_all 之前的迁移（如重建表）
        await _run_pre_migrations(conn)

        from backend.models.user import User  # noqa: F401
        from backend.models.resume import Resume  # noqa: F401
        from backend.models.agent_session import AgentSession  # noqa: F401
        from backend.models.agent_loop_state import AgentLoopState  # noqa: F401
        from backend.models.uploaded_file import UploadedFile  # noqa: F401
        from backend.models.analysis_report import AnalysisReport  # noqa: F401
        from backend.models.user_settings import UserSettings  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

        # create_all 之后的增量迁移（添加新列等）
        await _run_post_migrations(conn)


async def _run_pre_migrations(conn):
    """在 create_all 之前执行的迁移（需要重建表等操作）"""

    # 迁移 resumes 表：移除 UNIQUE(user_id) 约束，添加 version 和 name 列
    # SQLite 无法 ALTER TABLE DROP CONSTRAINT，只能重建表
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='resumes'"
    ))
    if result.scalar():
        # 检查是否存在 UNIQUE 索引（判断是否需要迁移）
        idx = await conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='ix_resumes_user_id'"
        ))
        idx_row = idx.scalar()
        needs_rebuild = idx_row and 'UNIQUE' in (idx_row or '').upper()

        if needs_rebuild:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS resumes_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    version INTEGER NOT NULL DEFAULT 1,
                    name VARCHAR(100),
                    basic_info JSON,
                    education JSON,
                    internship_exp JSON,
                    project_exp JSON,
                    personal_strengths JSON,
                    created_at DATETIME DEFAULT (datetime('now')),
                    updated_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            await conn.execute(text("""
                INSERT INTO resumes_new (id, user_id, version, name, basic_info, education, internship_exp, project_exp, personal_strengths, created_at, updated_at)
                SELECT id, user_id, 1, NULL, basic_info, education, internship_exp, project_exp, personal_strengths, created_at, updated_at FROM resumes
            """))
            await conn.execute(text("DROP TABLE resumes"))
            await conn.execute(text("ALTER TABLE resumes_new RENAME TO resumes"))

    # 清理旧的 resume_history 表（已合并到 resumes）
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='resume_history'"
    ))
    if result.scalar():
        await conn.execute(text("DROP TABLE resume_history"))

    # 迁移 uploaded_files 表：移除 ref_count 列（改用孤儿文件检查器）
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='uploaded_files'"
    ))
    if result.scalar():
        # 检查是否还存在 ref_count 列
        pragma = await conn.execute(text("PRAGMA table_info(uploaded_files)"))
        columns = [row[1] for row in pragma.fetchall()]
        if "ref_count" in columns:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS uploaded_files_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    original_name VARCHAR(255) NOT NULL,
                    storage_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(20) NOT NULL,
                    file_size INTEGER NOT NULL,
                    content_hash VARCHAR(64) NOT NULL,
                    raw_text TEXT,
                    char_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            await conn.execute(text("""
                INSERT INTO uploaded_files_new (id, user_id, original_name, storage_path, file_type, file_size, content_hash, raw_text, char_count, created_at)
                SELECT id, user_id, original_name, storage_path, file_type, file_size, content_hash, raw_text, char_count, created_at FROM uploaded_files
            """))
            await conn.execute(text("DROP TABLE uploaded_files"))
            await conn.execute(text("ALTER TABLE uploaded_files_new RENAME TO uploaded_files"))

    # 迁移 agent_sessions 表：移除废弃列（stage, pending_file_ids, usage, turn_count, compact_count, summary_token_checkpoint, error）
    # tool_results 已在 post_migrations 中重命名为 key_data，这里一并重建
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_sessions'"
    ))
    if result.scalar():
        pragma = await conn.execute(text("PRAGMA table_info(agent_sessions)"))
        columns = [row[1] for row in pragma.fetchall()]
        # 检查是否有旧列需要移除
        old_columns = {"stage", "pending_file_ids", "usage", "turn_count", "compact_count", "summary_token_checkpoint", "error", "tool_results"}
        if old_columns & set(columns):
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_sessions_new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    scenario VARCHAR(20) NOT NULL,
                    title VARCHAR(200) DEFAULT '',
                    messages TEXT NOT NULL DEFAULT '[]',
                    key_data TEXT DEFAULT '{}',
                    uploaded_file_ids TEXT DEFAULT '[]',
                    summary TEXT DEFAULT '',
                    created_at DATETIME DEFAULT (datetime('now')),
                    updated_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            # 确定 key_data 列的来源（可能是 tool_results 或已重命名的 key_data）
            src_key = "tool_results" if "tool_results" in columns else "key_data"
            await conn.execute(text(f"""
                INSERT INTO agent_sessions_new (id, user_id, scenario, title, messages, key_data, uploaded_file_ids, summary, created_at, updated_at)
                SELECT id, user_id, scenario, COALESCE(title, ''), messages, COALESCE({src_key}, '{{}}'), COALESCE(uploaded_file_ids, '[]'), COALESCE(summary, ''), created_at, updated_at FROM agent_sessions
            """))
            await conn.execute(text("DROP TABLE agent_sessions"))
            await conn.execute(text("ALTER TABLE agent_sessions_new RENAME TO agent_sessions"))


async def _run_post_migrations(conn):
    """在 create_all 之后执行的增量迁移（添加新列）"""
    migrations = [
        "ALTER TABLE agent_sessions ADD COLUMN uploaded_file_ids TEXT DEFAULT '[]'",
        "ALTER TABLE agent_sessions ADD COLUMN title VARCHAR(200) DEFAULT ''",
        "ALTER TABLE analysis_reports ADD COLUMN status VARCHAR(20) DEFAULT 'in_progress'",
        "ALTER TABLE analysis_reports ADD COLUMN updated_at DATETIME",
        "ALTER TABLE user_settings ADD COLUMN base_url VARCHAR(500)",
        "ALTER TABLE agent_loop_state ADD COLUMN summary_update_count INTEGER DEFAULT 0",
    ]
    for sql in migrations:
        try:
            await conn.execute(text(sql))
        except Exception:
            # 列已存在，忽略
            pass
