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


class ResumeResponse(BaseModel):
    id: int
    user_id: int
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
    id: int
    created_at: datetime
    changed_fields: list[str]

    class Config:
        from_attributes = True


class RestoreRequest(BaseModel):
    history_id: int
