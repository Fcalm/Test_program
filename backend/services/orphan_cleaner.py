"""孤儿文件检查服务

定期扫描 uploaded_files 表，删除无任何 agent_session 引用的文件。
替代原有的 ref_count 机制，基于 session 的 uploaded_file_ids 做引用关系判断。
"""

import json
import logging
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.uploaded_file import UploadedFile
from backend.models.agent_session import AgentSession
from backend.database import async_session

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")


async def clean_orphan_files(db: AsyncSession) -> dict:
    """扫描所有 uploaded_files，删除无 session 引用的文件

    Returns:
        {"scanned": int, "deleted": int, "errors": int}
    """
    # 1. 收集所有 session 引用的文件 ID
    result = await db.execute(
        select(AgentSession.uploaded_file_ids).where(
            AgentSession.uploaded_file_ids.isnot(None),
            AgentSession.uploaded_file_ids != "[]",
        )
    )
    referenced_ids: set[int] = set()
    for row in result.scalars().all():
        try:
            ids = json.loads(row)
            if isinstance(ids, list):
                referenced_ids.update(int(fid) for fid in ids if fid)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    # 2. 查询所有文件
    files_result = await db.execute(select(UploadedFile))
    all_files = files_result.scalars().all()

    # 3. 删除无引用的文件
    deleted = 0
    errors = 0
    for f in all_files:
        if f.id not in referenced_ids:
            try:
                full_path = UPLOAD_DIR / f.storage_path
                if full_path.exists():
                    full_path.unlink()
                await db.delete(f)
                deleted += 1
            except Exception as e:
                errors += 1
                logger.warning("删除孤儿文件失败: file_id=%s, error=%s", f.id, e)

    if deleted > 0:
        await db.flush()

    stats = {"scanned": len(all_files), "deleted": deleted, "errors": errors}
    if deleted > 0 or errors > 0:
        logger.info("孤儿文件清理完成: %s", stats)

    return stats


async def run_orphan_cleanup():
    """独立运行孤儿清理（使用独立 session，适合后台任务）"""
    async with async_session() as db:
        try:
            result = await clean_orphan_files(db)
            await db.commit()
            return result
        except Exception as e:
            await db.rollback()
            logger.error("孤儿文件清理异常: %s", e)
            return {"scanned": 0, "deleted": 0, "errors": 1}
