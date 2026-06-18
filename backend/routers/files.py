"""文件上传 API 路由"""

from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.models.uploaded_file import UploadedFile, FileText
from backend.services.file_storage import (
    save_and_extract,
    get_user_files,
    get_file_with_text,
    delete_file,
)
from backend.utils.auth import get_current_user

router = APIRouter(prefix="/files", tags=["文件管理"])


# ========== Schemas ==========

class FileUploadResponse(BaseModel):
    file_id: int
    original_name: str
    file_type: str
    file_size: int
    char_count: int = Field(default=0, description="提取的文本字符数，0 表示提取失败")
    created_at: datetime


class FileInfo(BaseModel):
    file_id: int
    original_name: str
    file_type: str
    file_size: int
    char_count: int
    created_at: datetime


class FileListResponse(BaseModel):
    files: list[FileInfo]


# ========== Endpoints ==========

@router.post("/upload", response_model=FileUploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(..., description="文件（PDF/DOCX）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传文件，自动提取文本"""
    uploaded, error = await save_and_extract(db, current_user.id, file)
    if error:
        raise HTTPException(status_code=400, detail=error)

    char_count = uploaded.text.char_count if uploaded.text else 0

    return FileUploadResponse(
        file_id=uploaded.id,
        original_name=uploaded.original_name,
        file_type=uploaded.file_type,
        file_size=uploaded.file_size,
        char_count=char_count,
        created_at=uploaded.created_at,
    )


@router.get("", response_model=FileListResponse)
async def list_files(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的所有文件"""
    files = await get_user_files(db, current_user.id)
    items = []
    for f in files:
        items.append(FileInfo(
            file_id=f.id,
            original_name=f.original_name,
            file_type=f.file_type,
            file_size=f.file_size,
            char_count=f.text.char_count if f.text else 0,
            created_at=f.created_at,
        ))
    return FileListResponse(files=items)


@router.get("/{file_id}")
async def get_file_info(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个文件信息"""
    result = await get_file_with_text(db, file_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")

    uploaded, text = result
    return {
        "file_id": uploaded.id,
        "original_name": uploaded.original_name,
        "file_type": uploaded.file_type,
        "file_size": uploaded.file_size,
        "char_count": text.char_count if text else 0,
        "created_at": uploaded.created_at,
        "raw_preview": text.raw_text[:500] if text else None,
    }


@router.delete("/{file_id}", status_code=204)
async def delete_file_endpoint(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除文件"""
    error = await delete_file(db, file_id, current_user.id)
    if error:
        raise HTTPException(status_code=404, detail=error)
