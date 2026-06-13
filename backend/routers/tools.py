"""
工具测试路由 —— 临时入口，agent 开发后删除此文件
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.schemas.jd import JDParseRequest, JDParseResponse
from backend.schemas.resume_parser import ResumeParseResponse
from backend.services.jd_parser import parse_jd, JD_KEYWORDS
from backend.services.resume_parser import parse_resume
from backend.services.resume import get_resume, create_resume, update_resume
from backend.schemas.resume import ResumeResponse
from backend.utils.auth import get_current_user

router = APIRouter(prefix="/tools", tags=["工具测试（临时）"])


@router.post("/parse-jd", response_model=JDParseResponse)
async def api_parse_jd(req: JDParseRequest):
    """解析 JD 文本为结构化 JSON"""
    return await parse_jd(req.text)


@router.get("/jd-keywords")
async def get_jd_keywords():
    """获取 JD 关键词列表（供前端检测用）"""
    return {"keywords": JD_KEYWORDS}


@router.post("/upload-resume", response_model=ResumeResponse)
async def upload_resume(
    file: UploadFile = File(..., description="简历文件（PDF/DOCX）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传简历文件，解析内容并更新简历数据"""
    # 读取文件内容
    file_bytes = await file.read()

    # 解析简历
    parse_result = await parse_resume(file.filename, file_bytes)

    if not parse_result.success:
        raise HTTPException(status_code=400, detail=parse_result.error)

    # 将解析结果转为简历数据格式
    data = parse_result.data
    resume_data = {
        "basic_info": data.basic_info,
        "education": data.education,
        "internship_exp": data.internship_exp,
        "project_exp": data.project_exp,
        "personal_strengths": data.personal_strengths,
    }

    # 更新或创建简历
    existing = await get_resume(db, current_user.id)
    if existing:
        resume = await update_resume(db, existing, resume_data)
    else:
        resume = await create_resume(db, current_user.id, resume_data)

    return ResumeResponse.model_validate(resume, from_attributes=True)
