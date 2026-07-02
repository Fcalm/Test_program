from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.schemas.resume import ResumeCreate, ResumeResponse, HistoryItem, UpdateHistoryNameRequest
from backend.services.resume_history import (
    get_resume,
    create_resume,
    update_resume,
    get_history_list,
    restore_history,
    update_history_name,
)
from backend.utils.auth import get_current_user

router = APIRouter(prefix="/resume", tags=["简历"])


@router.get("", response_model=ResumeResponse)
async def read_resume(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的简历，无简历时返回空模板"""
    resume = await get_resume(db, current_user.id)
    if not resume:
        return ResumeResponse(
            id=0,
            user_id=current_user.id,
            basic_info=None,
            education=None,
            internship_exp=None,
            project_exp=None,
            personal_strengths=None,
            has_resume=False,
        )
    return ResumeResponse.model_validate(resume, from_attributes=True)


@router.post("", response_model=ResumeResponse, status_code=status.HTTP_201_CREATED)
async def save_resume(
    data: ResumeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """首次保存简历（AI 生成后调用）"""
    existing = await get_resume(db, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="简历已存在，请使用 PUT 更新")

    # 提取 history_name 并从 data 中移除
    resume_data = data.model_dump()
    history_name = resume_data.pop("history_name", None)

    resume = await create_resume(db, current_user.id, resume_data, name=history_name)
    return ResumeResponse.model_validate(resume, from_attributes=True)


@router.put("", response_model=ResumeResponse)
async def edit_resume(
    data: ResumeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑更新简历（自动记录历史）"""
    resume = await get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在，请先创建")

    # 提取 history_name 并从 data 中移除
    resume_data = data.model_dump()
    history_name = resume_data.pop("history_name", None)

    resume = await update_resume(db, resume, resume_data, name=history_name)
    return ResumeResponse.model_validate(resume, from_attributes=True)


@router.get("/history", response_model=list[HistoryItem])
async def read_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取历史版本列表"""
    resume = await get_resume(db, current_user.id)
    if not resume:
        return []

    history_list = await get_history_list(db, resume.id)
    return [HistoryItem.model_validate(h, from_attributes=True) for h in history_list]


@router.post("/history/{history_id}/restore", response_model=ResumeResponse)
async def restore_version(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """恢复到某历史版本"""
    from sqlalchemy import select
    from backend.models.resume import ResumeHistory

    resume = await get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    result = await db.execute(
        select(ResumeHistory).where(
            ResumeHistory.id == history_id,
            ResumeHistory.resume_id == resume.id,
        )
    )
    history = result.scalar_one_or_none()
    if not history:
        raise HTTPException(status_code=404, detail="历史版本不存在")

    resume = await restore_history(db, resume, history)
    return ResumeResponse.model_validate(resume, from_attributes=True)


@router.put("/history/{history_id}/name")
async def rename_history(
    history_id: int,
    data: UpdateHistoryNameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改历史版本名称"""
    resume = await get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    success = await update_history_name(db, history_id, resume.id, data.name)
    if not success:
        raise HTTPException(status_code=404, detail="历史版本不存在")

    return {"message": "更新成功"}


@router.delete("/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除历史版本"""
    from sqlalchemy import select
    from backend.models.resume import ResumeHistory

    resume = await get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    result = await db.execute(
        select(ResumeHistory).where(
            ResumeHistory.id == history_id,
            ResumeHistory.resume_id == resume.id,
        )
    )
    history = result.scalar_one_or_none()
    if not history:
        raise HTTPException(status_code=404, detail="历史版本不存在")

    await db.delete(history)
    await db.flush()

    return None
