from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.resume import Resume, ResumeHistory

# 简历中参与历史对比的字段
DIFF_FIELDS = ["basic_info", "education", "internship_exp", "project_exp", "personal_strengths"]


async def get_resume(db: AsyncSession, user_id: int) -> Resume | None:
    result = await db.execute(select(Resume).where(Resume.user_id == user_id))
    return result.scalar_one_or_none()


async def create_resume(db: AsyncSession, user_id: int, data: dict) -> Resume:
    resume = Resume(user_id=user_id, **data)
    db.add(resume)
    await db.flush()

    # 首次保存：全量快照
    history = ResumeHistory(
        resume_id=resume.id,
        snapshot=data,
        changed_fields=DIFF_FIELDS,
    )
    db.add(history)
    await db.flush()
    await db.refresh(resume)
    return resume


async def update_resume(db: AsyncSession, resume: Resume, data: dict) -> Resume:
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
        history = ResumeHistory(
            resume_id=resume.id,
            snapshot=snapshot,
            changed_fields=changed,
        )
        db.add(history)

    await db.flush()
    await db.refresh(resume)
    return resume


async def get_history_list(db: AsyncSession, resume_id: int) -> list[ResumeHistory]:
    result = await db.execute(
        select(ResumeHistory)
        .where(ResumeHistory.resume_id == resume_id)
        .order_by(ResumeHistory.created_at.desc())
    )
    return list(result.scalars().all())


async def restore_history(db: AsyncSession, resume: Resume, history: ResumeHistory) -> Resume:
    """恢复历史版本：将历史快照中的字段合并回简历"""
    for field in history.changed_fields:
        if field in history.snapshot:
            setattr(resume, field, history.snapshot[field])

    # 记录这次恢复操作为一条新历史
    restore_record = ResumeHistory(
        resume_id=resume.id,
        snapshot=history.snapshot,
        changed_fields=history.changed_fields,
    )
    db.add(restore_record)
    await db.flush()
    await db.refresh(resume)
    return resume
