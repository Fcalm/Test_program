"""文件上传、存储、文本提取服务"""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.uploaded_file import UploadedFile, FileText
from backend.services.resume_parser import extract_text, validate_file

# 上传目录
UPLOAD_DIR = Path("uploads")


def _ensure_upload_dir(user_id: int) -> Path:
    """确保用户上传目录存在"""
    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


async def save_and_extract(
    db: AsyncSession, user_id: int, file: UploadFile
) -> tuple[UploadedFile | None, str | None]:
    """
    保存文件并提取文本。
    返回 (UploadedFile, None) 成功，(None, error_msg) 失败。
    """
    # 读取文件内容
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # 校验
    error = validate_file(file.filename, file_size)
    if error:
        return None, error

    # 生成 UUID 文件名
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    new_name = f"{uuid.uuid4().hex}{ext}"

    # 保存到磁盘
    user_dir = _ensure_upload_dir(user_id)
    storage_path = user_dir / new_name
    storage_path.write_bytes(file_bytes)

    # 相对路径（用于 DB 存储）
    rel_path = f"{user_id}/{new_name}"

    # 插入文件记录
    uploaded = UploadedFile(
        user_id=user_id,
        original_name=file.filename,
        storage_path=rel_path,
        file_type=ext.lstrip("."),
        file_size=file_size,
    )
    db.add(uploaded)
    await db.flush()

    # 提取文本
    try:
        raw_text = extract_text(file.filename, file_bytes)
        if raw_text and len(raw_text.strip()) >= 10:
            file_text = FileText(
                file_id=uploaded.id,
                raw_text=raw_text,
                char_count=len(raw_text),
            )
            db.add(file_text)
            await db.flush()
    except Exception:
        # 提取失败不影响文件保存
        pass

    return uploaded, None


async def get_user_files(db: AsyncSession, user_id: int) -> list[UploadedFile]:
    """获取用户的所有文件"""
    stmt = (
        select(UploadedFile)
        .where(UploadedFile.user_id == user_id)
        .order_by(UploadedFile.created_at.desc())
        .options(selectinload(UploadedFile.text))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_file_with_text(
    db: AsyncSession, file_id: int, user_id: int
) -> tuple[UploadedFile, FileText | None] | None:
    """获取文件及其提取的文本，校验用户权限"""
    stmt = (
        select(UploadedFile)
        .where(UploadedFile.id == file_id, UploadedFile.user_id == user_id)
        .options(selectinload(UploadedFile.text))
    )
    result = await db.execute(stmt)
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        return None
    return uploaded, uploaded.text


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

    # 删除 DB 记录（cascade 会删除 file_texts）
    await db.delete(uploaded)
    await db.flush()
    return None


async def get_file_text_for_agent(
    db: AsyncSession, file_id: int, user_id: int, max_chars: int = 8000
) -> str | None:
    """供 Agent 工具调用，返回文件文本内容"""
    result = await get_file_with_text(db, file_id, user_id)
    if not result:
        return None
    uploaded, text = result
    if not text:
        return None
    return text.raw_text[:max_chars]
