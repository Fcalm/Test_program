from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.resume import Resume

# 简历数据字段
RESUME_FIELDS = ["basic_info", "education", "internship_exp", "project_exp", "personal_strengths"]

# 历史版本上限
MAX_VERSIONS = 50


async def _next_version(db: AsyncSession, user_id: int) -> int:
    """获取下一个版本号"""
    result = await db.execute(
        select(func.max(Resume.version)).where(Resume.user_id == user_id)
    )
    max_ver = result.scalar() or 0
    return max_ver + 1


async def _cleanup_old_versions(db: AsyncSession, user_id: int) -> None:
    """清理超出上限的旧版本（保留最新的，删除最旧的）"""
    count_result = await db.execute(
        select(func.count()).where(Resume.user_id == user_id)
    )
    total = count_result.scalar() or 0

    if total <= MAX_VERSIONS:
        return

    excess = total - MAX_VERSIONS
    old_records = await db.execute(
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.version.asc())
        .limit(excess)
    )
    for record in old_records.scalars().all():
        await db.delete(record)


async def get_resume(db: AsyncSession, user_id: int) -> Resume | None:
    """获取用户的最新版本简历"""
    result = await db.execute(
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_resume_by_id(db: AsyncSession, resume_id: int) -> Resume | None:
    """按 ID 获取指定版本"""
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    return result.scalar_one_or_none()


async def create_resume(db: AsyncSession, user_id: int, data: dict, name: str | None = None) -> Resume:
    """创建简历（自动分配版本号）"""
    version = await _next_version(db, user_id)
    resume = Resume(
        user_id=user_id,
        version=version,
        name=name or _default_name(),
        **data,
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)
    return resume


async def update_resume(db: AsyncSession, resume: Resume, data: dict, name: str | None = None) -> Resume:
    """更新简历：有变化时创建新版本行"""
    # 检查是否有实际变化
    changed = []
    for field in RESUME_FIELDS:
        new_val = data.get(field)
        old_val = getattr(resume, field)
        if new_val is not None and new_val != old_val:
            changed.append(field)

    if not changed:
        return resume

    # 创建新版本行
    new_version = await _next_version(db, resume.user_id)
    new_resume = Resume(
        user_id=resume.user_id,
        version=new_version,
        name=name or _default_name(),
        **{field: data.get(field, getattr(resume, field)) for field in RESUME_FIELDS},
    )
    db.add(new_resume)
    await db.flush()

    # 清理旧版本
    await _cleanup_old_versions(db, resume.user_id)

    await db.refresh(new_resume)
    return new_resume


async def get_history_list(db: AsyncSession, user_id: int, limit: int = 50, offset: int = 0) -> list[Resume]:
    """获取用户的所有版本列表（最新在前）"""
    result = await db.execute(
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.version.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def restore_version(db: AsyncSession, target: Resume) -> Resume:
    """恢复到指定版本：更新当前最新版本的内容为目标版本的副本"""
    current = await get_resume(db, target.user_id)
    if not current:
        return target
    if current.id == target.id:
        return current

    for field in RESUME_FIELDS:
        setattr(current, field, getattr(target, field))

    await db.flush()
    await db.refresh(current)
    return current


async def update_version_name(db: AsyncSession, resume_id: int, user_id: int, name: str) -> bool:
    """修改版本名称"""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        return False

    resume.name = name
    await db.flush()
    return True


async def delete_version(db: AsyncSession, resume_id: int, user_id: int) -> bool:
    """删除指定版本"""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        return False

    await db.delete(resume)
    await db.flush()
    return True


def _default_name() -> str:
    now = datetime.now()
    return f"{now.year}年{now.month}月{now.day}日 {now.hour:02d}:{now.minute:02d}"
