"""文件上传、存储、文本提取服务"""

import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.uploaded_file import UploadedFile
from backend.services.resume_parser import extract_text, validate_file

logger = logging.getLogger(__name__)

# 上传目录
UPLOAD_DIR = Path("uploads")

# 文件数上限
MAX_FILES_PER_USER = 100


def _ensure_upload_dir(user_id: int) -> Path:
    """确保用户上传目录存在"""
    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


async def _cleanup_old_files(db: AsyncSession, user_id: int) -> None:
    """清理用户超出上限的旧文件"""
    count_result = await db.execute(
        select(func.count()).where(UploadedFile.user_id == user_id)
    )
    total = count_result.scalar() or 0

    if total <= MAX_FILES_PER_USER:
        return

    excess = total - MAX_FILES_PER_USER
    old_files = await db.execute(
        select(UploadedFile)
        .where(UploadedFile.user_id == user_id)
        .order_by(UploadedFile.created_at.asc())
        .limit(excess)
    )
    for f in old_files.scalars().all():
        full_path = UPLOAD_DIR / f.storage_path
        if full_path.exists():
            full_path.unlink()
        await db.delete(f)


async def save_and_extract(
    db: AsyncSession, user_id: int, file: UploadFile
) -> tuple[UploadedFile | None, str | None]:
    """
    保存文件并提取文本，支持 SHA256 查重。
    返回 (UploadedFile, None) 成功，(None, error_msg) 失败。
    """
    file_bytes = await file.read()
    file_size = len(file_bytes)

    error = validate_file(file.filename, file_size)
    if error:
        return None, error

    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # 查重：同一用户上传相同文件，直接返回已有记录
    existing = await db.execute(
        select(UploadedFile).where(
            UploadedFile.user_id == user_id,
            UploadedFile.content_hash == content_hash,
        )
    )
    duplicate = existing.scalar_one_or_none()
    if duplicate:
        return duplicate, None

    # 保存新文件
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    new_name = f"{uuid.uuid4().hex}{ext}"

    user_dir = _ensure_upload_dir(user_id)
    storage_path = user_dir / new_name
    storage_path.write_bytes(file_bytes)

    rel_path = f"{user_id}/{new_name}"

    raw_text = None
    char_count = 0
    try:
        raw_text = extract_text(file.filename, file_bytes)
        if raw_text and len(raw_text.strip()) < 10:
            raw_text = None
        else:
            char_count = len(raw_text)
    except Exception:
        pass

    uploaded = UploadedFile(
        user_id=user_id,
        original_name=file.filename,
        storage_path=rel_path,
        file_type=ext.lstrip("."),
        file_size=file_size,
        content_hash=content_hash,
        raw_text=raw_text,
        char_count=char_count,
    )
    db.add(uploaded)
    await db.flush()

    await _cleanup_old_files(db, user_id)

    await db.refresh(uploaded)
    return uploaded, None


async def get_user_files(db: AsyncSession, user_id: int) -> list[UploadedFile]:
    """获取用户的所有文件"""
    stmt = (
        select(UploadedFile)
        .where(UploadedFile.user_id == user_id)
        .order_by(UploadedFile.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_file_with_text(
    db: AsyncSession, file_id: int, user_id: int
) -> UploadedFile | None:
    """获取文件，校验用户权限"""
    stmt = select(UploadedFile).where(
        UploadedFile.id == file_id, UploadedFile.user_id == user_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_file(db: AsyncSession, file_id: int, user_id: int) -> str | None:
    """删除文件，返回错误信息或 None"""
    stmt = select(UploadedFile).where(
        UploadedFile.id == file_id, UploadedFile.user_id == user_id
    )
    result = await db.execute(stmt)
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        return "文件不存在"

    # 删除磁盘文件
    full_path = UPLOAD_DIR / uploaded.storage_path
    if full_path.exists():
        full_path.unlink()

    await db.delete(uploaded)
    await db.flush()
    return None


async def get_file_text_for_agent(
    db: AsyncSession, file_id: int, user_id: int, max_chars: int = 8000
) -> str | None:
    """供 Agent 工具调用，返回文件文本内容"""
    uploaded = await get_file_with_text(db, file_id, user_id)
    if not uploaded or not uploaded.raw_text:
        return None
    return uploaded.raw_text[:max_chars]
