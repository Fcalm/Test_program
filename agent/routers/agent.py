"""Agent API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import json

from backend.database import get_db
from backend.models.user import User
from backend.services.resume import get_resume
from backend.services.file_storage import get_file_text_for_agent
from backend.services.agent_session import load_session, save_session
from backend.utils.auth import get_current_user
from agent.core.state import AgentState
from agent.core.loop import chat_with_agent, chat_with_agent_stream
from agent.services.match_score import calculate_match_score

router = APIRouter(prefix="/agent", tags=["AI Agent"])


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = ""
    file_ids: list[int] = Field(default_factory=list, description="文件 ID 列表，上传文件后传入")
    session_id: str | None = Field(None, description="会话 ID，为空则创建新会话")
    scenario: str = Field("resume", description="场景：resume/interview/job_find/analysis")
    stage: str = Field("", description="当前阶段")


class ChatResponse(BaseModel):
    """聊天响应"""
    response: str
    session_id: str
    stage: str = ""
    thinking: str = ""


class MatchScoreRequest(BaseModel):
    """匹配分数请求"""
    jd_data: dict
    resume_data: dict


class MatchScoreResponse(BaseModel):
    """匹配分数响应"""
    total_score: int
    skill_score: int
    experience_score: int
    education_score: int
    keyword_score: int
    matched_keywords: list[str]
    missing_keywords: list[str]
    suggestions: list[str]


async def _get_resume_tool_result(user: User, db: AsyncSession) -> dict | None:
    """获取用户简历数据，返回工具结果格式"""
    resume = await get_resume(db, user.id)
    if resume and resume.basic_info:
        return {
            "success": True,
            "basic_info": resume.basic_info,
            "education": resume.education,
            "internship_exp": resume.internship_exp,
            "project_exp": resume.project_exp,
            "personal_strengths": resume.personal_strengths,
        }
    return None


async def _build_message_with_files(
    user_text: str,
    file_ids: list[int],
    user: User,
    db: AsyncSession,
) -> str:
    """构建注入文件内容后的用户消息

    有文字说明时：
        {user_text}\n\n[附件]\nfile_id=42 resume.pdf:\n{raw_text}

    没有文字说明（只上传文件）：
        用户上传了文件（file_id=42, resume.pdf），内容如下：\n\n{raw_text}
    """
    if not file_ids:
        return user_text

    # 读取文件内容
    file_parts = []
    for file_id in file_ids:
        text = await get_file_text_for_agent(db, file_id, user.id, max_chars=8000)
        if text:
            file_parts.append(f"[file_id={file_id}]\n{text}")

    if not file_parts:
        return user_text

    files_block = "\n\n".join(file_parts)

    if user_text.strip():
        return f"{user_text}\n\n[附件]\n{files_block}"
    else:
        return f"用户上传了文件，内容如下：\n\n{files_block}"


async def _load_or_create_state(
    user: User,
    db: AsyncSession,
    session_id: str | None,
    scenario: str,
    stage: str,
) -> AgentState:
    """加载或创建 AgentState

    如果提供了 session_id，尝试从数据库加载；
    否则创建新 State 并预加载用户简历数据。
    """
    # 尝试从数据库加载
    if session_id:
        state_data = await load_session(db, session_id)
        if state_data:
            # 验证用户权限
            if state_data.get("user_id") == user.id:
                return AgentState.restore(state_data)

    # 创建新 State
    state = AgentState(
        user_id=user.id,
        scenario=scenario,
        stage=stage,
    )

    # 预加载用户简历数据到 tool_results
    resume_data = await _get_resume_tool_result(user, db)
    if resume_data:
        state.set_tool_result("get_resume_table", resume_data)

    return state


async def _save_state(state: AgentState, db: AsyncSession) -> None:
    """保存 State 到数据库"""
    snapshot = state.snapshot()
    await save_session(db, snapshot)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """与 AI Agent 对话"""
    try:
        # 加载或创建 State
        state = await _load_or_create_state(
            current_user, db,
            request.session_id,
            request.scenario,
            request.stage,
        )

        # 构建消息（注入文件内容）
        message = await _build_message_with_files(
            request.message, request.file_ids, current_user, db
        )

        # 执行对话
        result = await chat_with_agent(
            message=message,
            state=state,
            db=db,
        )

        # 保存 State
        await _save_state(state, db)

        return ChatResponse(
            response=result["response"],
            session_id=state.session_id,
            stage=result.get("stage", ""),
            thinking=result.get("thinking", ""),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败：{str(e)}")


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """与 AI Agent 对话（流式输出）"""
    try:
        # 加载或创建 State
        state = await _load_or_create_state(
            current_user, db,
            request.session_id,
            request.scenario,
            request.stage,
        )

        # 构建消息（注入文件内容）
        message = await _build_message_with_files(
            request.message, request.file_ids, current_user, db
        )

        async def event_generator():
            """SSE 事件生成器"""
            async for chunk in chat_with_agent_stream(
                message=message,
                state=state,
                db=db,
            ):
                event_data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

            # 流结束后保存 State
            await _save_state(state, db)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败：{str(e)}")


@router.post("/match-score", response_model=MatchScoreResponse)
async def get_match_score(
    request: MatchScoreRequest,
    current_user: User = Depends(get_current_user),
):
    """计算 JD 与简历的匹配分数"""
    try:
        result = calculate_match_score(request.jd_data, request.resume_data)
        return MatchScoreResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"计算失败：{str(e)}")


@router.get("/health")
async def health_check():
    """Agent 健康检查"""
    from backend.config import settings
    return {
        "status": "ok",
        "model": settings.LLM_MODEL,
        "has_api_key": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key"),
    }
