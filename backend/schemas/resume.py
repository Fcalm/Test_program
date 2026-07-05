from datetime import datetime
from pydantic import BaseModel, Field


class BasicInfo(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""


class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    major: str = ""
    time: str = ""
    courses: str = ""


class InternshipItem(BaseModel):
    company: str = ""
    role: str = ""
    time: str = ""
    description: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str = ""
    role: str = ""
    time: str = ""
    description: list[str] = Field(default_factory=list)


class ResumeCreate(BaseModel):
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    education: list[EducationItem] = Field(default_factory=list)
    internship_exp: list[InternshipItem] = Field(default_factory=list)
    project_exp: list[ProjectItem] = Field(default_factory=list)
    personal_strengths: list[str] = Field(default_factory=list)
    history_name: str | None = Field(None, description="版本名称")


class ResumeResponse(BaseModel):
    id: int
    user_id: int
    version: int = 1
    name: str | None = None
    basic_info: dict | None = None
    education: list | None = None
    internship_exp: list | None = None
    project_exp: list | None = None
    personal_strengths: list | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    has_resume: bool = True

    class Config:
        from_attributes = True


class HistoryItem(BaseModel):
    """版本列表项 — 包含完整简历数据"""
    id: int
    version: int
    name: str | None = None
    basic_info: dict | None = None
    education: list | None = None
    internship_exp: list | None = None
    project_exp: list | None = None
    personal_strengths: list | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateHistoryNameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="版本名称")
