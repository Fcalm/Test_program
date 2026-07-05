"""面试分析报告 Schema"""

from datetime import datetime

from pydantic import BaseModel, Field


class AnalysisReportResponse(BaseModel):
    """分析报告响应"""

    id: int
    session_id: str
    report_data: dict
    status: str = "in_progress"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
