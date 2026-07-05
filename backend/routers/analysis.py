"""面试分析报告 API 路由"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.schemas.analysis import AnalysisReportResponse
from backend.services.analysis import get_report_by_session, merge_report_data
from backend.services.agent_session import load_session, save_session, delete_session
from backend.utils.auth import get_current_user
from agent.core.loop import chat_with_agent
from agent.core.state import AgentState
from backend.provider_config import resolve_config, ResolvedConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["面试分析"])


class AnalysisTriggerRequest(BaseModel):
    """分析触发请求"""
    interview_session_id: str = Field(..., description="面试会话 ID")
    analysis_type: str = Field(..., description="分析类型：round / final")
    round: int = Field(1, description="当前轮次（仅 round 类型需要）")
    messages: list[dict] = Field(default_factory=list, description="面试消息记录")


class AnalysisTriggerResponse(BaseModel):
    """分析触发响应"""
    session_id: str
    report_data: dict
    status: str


def _build_analysis_prompt(req: AnalysisTriggerRequest) -> str:
    """构建分析 agent 的 prompt"""
    # 格式化面试记录（过滤工具调用和系统消息）
    formatted_messages = []
    for msg in req.messages:
        role = msg.get("role", "")
        if role == "tool" or role == "system":
            continue
        if role == "assistant" and msg.get("tool_calls"):
            continue
        display_role = "面试者" if role == "user" else "面试官"
        content = msg.get("content", "")
        if content:
            formatted_messages.append(f"{display_role}：{content}")

    chat_history = "\n\n".join(formatted_messages)

    if req.analysis_type == "round":
        return f"""【分析类型】轮次分析
【轮次】第 {req.round} 轮

【面试记录】
{chat_history}

请分析本轮面试表现，按规则生成 JSON 格式的分析结果。"""
    else:
        return f"""【分析类型】最终汇总

【完整面试记录】
{chat_history}

请生成最终汇总分析，包括各维度评分和改进建议。"""


def _extract_json_from_response(response: str) -> dict | None:
    """从 agent 响应中提取 JSON"""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 块
    import re
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取 { ... }
    brace_match = re.search(r'\{[\s\S]*\}', response)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def _run_analysis(
    user: User,
    db: AsyncSession,
    req: AnalysisTriggerRequest,
    resolved_config: ResolvedConfig,
    max_retries: int = 3,
) -> dict:
    """运行分析 agent，支持重试

    分析失败重试三次；汇总失败不影响面试（静默处理）。
    """
    analysis_session_id = f"{req.interview_session_id}-analysis"

    # 从数据库加载面试会话的完整消息（确保数据完整）
    interview_session, _ = await load_session(db, req.interview_session_id)
    if interview_session and interview_session.get("messages"):
        req.messages = interview_session["messages"]

    # 加载已有分析 session 状态（支持多轮分析上下文累积）
    existing_session, existing_loop = await load_session(db, analysis_session_id)
    if existing_session:
        state = AgentState.restore(existing_session, existing_loop)
    else:
        state = AgentState(
            user_id=user.id,
            scenario="analysis",
            session_id=analysis_session_id,
        )

    # 构建 prompt
    prompt = _build_analysis_prompt(req)

    last_error = None
    for attempt in range(max_retries):
        try:
            result = await chat_with_agent(
                message=prompt,
                state=state,
                db=db,
                resolved_config=resolved_config,
            )

            # 保存分析 session 状态（保留上下文供后续轮次使用）
            await save_session(db, state.snapshot_session(), state.snapshot_loop())
            await db.flush()

            response_text = result.get("response", "")
            logger.info("分析 agent 响应（前500字）: %s", response_text[:500])
            report_json = _extract_json_from_response(response_text)

            if report_json:
                # 保存到数据库（使用 merge 逻辑）
                if req.analysis_type == "round":
                    report_json["status"] = "in_progress"
                else:
                    report_json["status"] = "completed"

                saved = await merge_report_data(
                    db=db,
                    user_id=user.id,
                    session_id=req.interview_session_id,
                    new_data=report_json,
                )

                # 最终汇总完成后，清理分析 agent session
                if req.analysis_type == "final":
                    try:
                        await delete_session(db, analysis_session_id, user.id)
                    except Exception as e:
                        logger.warning("清理分析 session 失败: %s", e)

                return {
                    "session_id": req.interview_session_id,
                    "report_data": saved.report_data,
                    "status": saved.status,
                }
            else:
                raise ValueError("无法从 agent 响应中提取 JSON")

        except Exception as e:
            last_error = e
            logger.warning(
                "分析失败 (第 %d/%d 次): %s",
                attempt + 1, max_retries, e,
            )

    # 重试耗尽
    logger.error("分析最终失败: %s", last_error)
    raise last_error


@router.post("/trigger", response_model=AnalysisTriggerResponse)
async def trigger_analysis(
    req: AnalysisTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """触发面试分析

    - round 类型：分析当前轮次
    - final 类型：生成最终汇总

    分析失败自动重试 3 次。
    """
    try:
        resolved_config = await resolve_config(current_user.id, db)
        result = await _run_analysis(current_user, db, req, resolved_config)
        return AnalysisTriggerResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"分析失败：{str(e)}",
        )


@router.get("/{session_id}", response_model=AnalysisReportResponse)
async def get_report(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定会话的分析报告"""
    report = await get_report_by_session(db, session_id)
    if not report or report.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="分析报告不存在")
    return AnalysisReportResponse.model_validate(report, from_attributes=True)
