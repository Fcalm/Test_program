from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.resume import Resume, ResumeHistory

# 简历中参与历史对比的字段
DIFF_FIELDS = ["basic_info", "education", "internship_exp", "project_exp", "personal_strengths"]

# 历史记录上限
MAX_HISTORY_PER_RESUME = 50


async def _cleanup_old_history(db: AsyncSession, resume_id: int) -> None:
    """清理超出上限的旧历史记录"""
    count_result = await db.execute(
        select(func.count()).where(ResumeHistory.resume_id == resume_id)
    )
    total = count_result.scalar() or 0

    if total <= MAX_HISTORY_PER_RESUME:
        return

    # 删除最旧的记录
    excess = total - MAX_HISTORY_PER_RESUME
    old_records = await db.execute(
        select(ResumeHistory)
        .where(ResumeHistory.resume_id == resume_id)
        .order_by(ResumeHistory.created_at.asc())
        .limit(excess)
    )
    for record in old_records.scalars().all():
        await db.delete(record)


async def get_resume(db: AsyncSession, user_id: int) -> Resume | None:
    result = await db.execute(select(Resume).where(Resume.user_id == user_id))
    return result.scalar_one_or_none()


async def create_resume(db: AsyncSession, user_id: int, data: dict, name: str | None = None) -> Resume:
    resume = Resume(user_id=user_id, **data)
    db.add(resume)
    await db.flush()

    # 首次保存：全量快照
    history = ResumeHistory(
        resume_id=resume.id,
        name=name,
        snapshot=data,
        changed_fields=DIFF_FIELDS,
    )
    db.add(history)
    await db.flush()
    await db.refresh(resume)
    return resume


async def update_resume(db: AsyncSession, resume: Resume, data: dict, name: str | None = None) -> Resume:
    # 收集实际变化的字段
    changed = []
    snapshot = {}
    for field in DIFF_FIELDS:
        new_val = data.get(field)
        old_val = getattr(resume, field)
        if new_val is not None and new_val != old_val:
            changed.append(field)
            snapshot[field] = new_val
            setattr(resume, field, new_val)

    # 有变化才记录历史
    if changed:
        # 如果没有指定名称，使用默认格式
        if not name:
            from datetime import datetime
            now = datetime.now()
            name = f"{now.year}年{now.month}月{now.day}日 {now.hour:02d}:{now.minute:02d}"

        history = ResumeHistory(
            resume_id=resume.id,
            name=name,
            snapshot=snapshot,
            changed_fields=changed,
        )
        db.add(history)
        await db.flush()

        # 清理旧历史
        await _cleanup_old_history(db, resume.id)

    await db.flush()
    await db.refresh(resume)
    return resume


async def update_history_name(db: AsyncSession, history_id: int, resume_id: int, name: str) -> bool:
    """更新历史记录名称"""
    result = await db.execute(
        select(ResumeHistory).where(
            ResumeHistory.id == history_id,
            ResumeHistory.resume_id == resume_id,
        )
    )
    history = result.scalar_one_or_none()
    if not history:
        return False

    history.name = name
    await db.flush()
    return True


async def get_history_list(
    db: AsyncSession, resume_id: int, limit: int = 50, offset: int = 0
) -> list[ResumeHistory]:
    result = await db.execute(
        select(ResumeHistory)
        .where(ResumeHistory.resume_id == resume_id)
        .order_by(ResumeHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def restore_history(db: AsyncSession, resume: Resume, history: ResumeHistory) -> Resume:
    """恢复历史版本：将历史快照中的字段合并回简历

    注意：恢复操作不会创建新的历史记录，避免历史记录无限增长。
    """
    for field in history.changed_fields:
        if field in history.snapshot:
            setattr(resume, field, history.snapshot[field])

    await db.flush()
    await db.refresh(resume)
    return resume
