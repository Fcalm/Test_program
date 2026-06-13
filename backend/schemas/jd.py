from pydantic import BaseModel, Field


class JDParsed(BaseModel):
    """JD 解析结果"""
    position: str = Field(default="", description="职位名称")
    company: str = Field(default="", description="公司名称")
    responsibilities: list[str] = Field(default_factory=list, description="岗位职责")
    requirements: list[str] = Field(default_factory=list, description="任职要求")
    salary: str = Field(default="", description="薪资范围")
    location: str = Field(default="", description="工作地点")
    benefits: list[str] = Field(default_factory=list, description="福利待遇")


class JDParseRequest(BaseModel):
    """JD 解析请求"""
    text: str = Field(..., min_length=10, description="JD 原始文本")


class JDParseResponse(BaseModel):
    """JD 解析响应"""
    success: bool
    data: JDParsed | None = None
    error: str | None = None
    method: str = Field(default="", description="解析方式: regex / llm")
