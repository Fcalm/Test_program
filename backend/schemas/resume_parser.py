from pydantic import BaseModel, Field


class ResumeParsedData(BaseModel):
    """简历解析结果"""
    basic_info: dict = Field(default_factory=dict, description="基本信息：name, phone, email")
    education: list[dict] = Field(default_factory=list, description="教育经历")
    internship_exp: list[dict] = Field(default_factory=list, description="实习经历")
    project_exp: list[dict] = Field(default_factory=list, description="项目经历")
    personal_strengths: list[str] = Field(default_factory=list, description="个人优势")


class ResumeParseResponse(BaseModel):
    """简历解析响应"""
    success: bool
    data: ResumeParsedData | None = None
    error: str | None = None
    method: str = Field(default="", description="解析方式: regex / llm")
    raw_text: str = Field(default="", description="提取的原始文本（调试用）")
