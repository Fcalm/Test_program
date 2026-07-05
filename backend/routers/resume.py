import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.schemas.resume import ResumeCreate, ResumeResponse, HistoryItem, UpdateHistoryNameRequest
from backend.services.resume_history import (
    get_resume,
    get_resume_by_id,
    create_resume,
    update_resume,
    get_history_list,
    restore_version,
    update_version_name,
    delete_version,
)
from backend.services.resume_export import generate_pdf, generate_docx
from backend.utils.auth import get_current_user

router = APIRouter(prefix="/resume", tags=["简历"])


@router.get("", response_model=ResumeResponse)
async def read_resume(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的最新简历，无简历时返回空模板"""
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
    """编辑更新简历（自动创建新版本）"""
    resume = await get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在，请先创建")

    resume_data = data.model_dump()
    history_name = resume_data.pop("history_name", None)

    resume = await update_resume(db, resume, resume_data, name=history_name)
    return ResumeResponse.model_validate(resume, from_attributes=True)


@router.get("/export")
async def export_resume(
    format: str = Query(..., pattern="^(pdf|docx)$", description="导出格式：pdf 或 docx"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出简历为 PDF 或 DOCX 文件"""
    resume = await get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="暂无简历数据")

    resume_data = {
        "basic_info": resume.basic_info,
        "education": resume.education,
        "internship_exp": resume.internship_exp,
        "project_exp": resume.project_exp,
        "personal_strengths": resume.personal_strengths,
    }

    # 用姓名作为默认文件名
    name = (resume.basic_info or {}).get("name", "") or "简历"
    filename = f"{name}的简历"

    if format == "pdf":
        content = generate_pdf(resume_data)
        media_type = "application/pdf"
        ext = "pdf"
    else:
        content = generate_docx(resume_data)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"

    # RFC 5987: 用 UTF-8 编码非 ASCII 文件名
    encoded = quote(f"{filename}.{ext}")
    disposition = f"attachment; filename=\"resume.{ext}\"; filename*=UTF-8''{encoded}"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


@router.get("/history", response_model=list[HistoryItem])
async def read_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有版本列表（最新在前）"""
    history_list = await get_history_list(db, current_user.id)
    return [HistoryItem.model_validate(h, from_attributes=True) for h in history_list]


@router.get("/history/{resume_id}", response_model=HistoryItem)
async def read_history_detail(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定版本的完整简历数据"""
    resume = await get_resume_by_id(db, resume_id)
    if not resume or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="版本不存在")
    return HistoryItem.model_validate(resume, from_attributes=True)


@router.post("/history/{resume_id}/restore", response_model=ResumeResponse)
async def restore_to_version(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """恢复到指定版本（创建新版本，内容为目标版本的副本）"""
    target = await get_resume_by_id(db, resume_id)
    if not target or target.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="版本不存在")

    restored = await restore_version(db, target)
    return ResumeResponse.model_validate(restored, from_attributes=True)


@router.put("/history/{resume_id}/name")
async def rename_version(
    resume_id: int,
    data: UpdateHistoryNameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改版本名称"""
    success = await update_version_name(db, resume_id, current_user.id, data.name)
    if not success:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"message": "更新成功"}


@router.delete("/history/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history_version(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除指定版本（不能删除最后一个版本）"""
    from sqlalchemy import select, func
    from backend.models.resume import Resume

    # 查询是否存在（不限 user_id，用于诊断）
    check = await db.execute(select(Resume).where(Resume.id == resume_id))
    found = check.scalar_one_or_none()
    count_r = await db.execute(select(func.count()).where(Resume.user_id == current_user.id))
    total = count_r.scalar() or 0

    if not found:
        raise HTTPException(status_code=404, detail=f"简历 id={resume_id} 不存在，当前用户共 {total} 个版本")
    if found.user_id != current_user.id:
        raise HTTPException(status_code=404, detail=f"简历 id={resume_id} 属于 user_id={found.user_id}，当前 user_id={current_user.id}")

    await db.delete(found)
    await db.flush()
    return None
