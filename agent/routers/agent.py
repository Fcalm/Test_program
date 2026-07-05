"""Agent API 路由"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import json

from backend.database import async_session, get_db
from backend.models.user import User
from backend.services.resume_history import get_resume
from backend.services.agent_session import load_session, save_session, list_user_sessions, delete_session
from backend.utils.auth import get_current_user
from backend.provider_config import resolve_config
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
    title: str = Field("", description="会话标题（可选）")
    resume_version_id: int | None = Field(None, description="指定简历版本 ID（用于面试场景）")


class ChatResponse(BaseModel):
    """聊天响应"""
    response: str
    session_id: str
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


async def _get_resume_tool_result(user: User, db: AsyncSession, version_id: int | None = None) -> dict | None:
    """获取用户简历数据，返回工具结果格式

    Args:
        version_id: 指定版本 ID，为 None 时获取最新版本
    """
    if version_id:
        from backend.services.resume_history import get_resume_by_id
        resume = await get_resume_by_id(db, version_id)
        # 验证所有权
        if not resume or resume.user_id != user.id:
            resume = await get_resume(db, user.id)
    else:
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
) -> str:
    """构建注入文件提示的用户消息

    注入格式：
        {user_text}\n\n用户上传了文件 [file_id=42]，使用 read_file 工具查看
    """
    if not file_ids:
        return user_text

    ids_str = ", ".join(f"file_id={fid}" for fid in file_ids)
    return f"{user_text}\n\n用户上传了文件 [{ids_str}]，使用 read_file 工具查看"


async def _load_or_create_state(
    user: User,
    db: AsyncSession,
    session_id: str | None,
    scenario: str,
    title: str = "",
    resume_version_id: int | None = None,
) -> AgentState:
    """加载或创建 AgentState

    如果提供了 session_id，尝试从数据库加载；
    否则创建新 State 并预加载用户简历数据。
    """
    # 尝试从数据库加载
    if session_id:
        session_data, loop_data = await load_session(db, session_id)
        if session_data:
            # 验证用户权限
            if session_data.get("user_id") == user.id:
                return AgentState.restore(session_data, loop_data)

    # 创建新 State
    state = AgentState(
        user_id=user.id,
        scenario=scenario,
        title=title,
    )

    # 预加载用户简历数据到 key_data
    resume_data = await _get_resume_tool_result(user, db, resume_version_id)
    if resume_data:
        state.set_key_data("get_resume_table", resume_data)

    return state


async def _save_state(state: AgentState, db: AsyncSession) -> None:
    """保存 State 到数据库（双表写入）"""
    session_data = state.snapshot_session()
    loop_data = state.snapshot_loop()
    await save_session(db, session_data, loop_data)


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
            request.title,
            request.resume_version_id,
        )

        # 构建消息（注入文件引用）
        message = await _build_message_with_files(
            request.message, request.file_ids
        )
        # 记录文件归属
        for fid in request.file_ids:
            if fid not in state.uploaded_file_ids:
                state.uploaded_file_ids.append(fid)

        # 解析配置
        resolved_config = await resolve_config(current_user.id, db)

        # 执行对话
        result = await chat_with_agent(
            message=message,
            state=state,
            db=db,
            resolved_config=resolved_config,
        )

        # 保存 State
        await _save_state(state, db)

        return ChatResponse(
            response=result["response"],
            session_id=state.session_id,
            thinking=result.get("thinking", ""),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败：{str(e)}")


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
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
            request.title,
            request.resume_version_id,
        )

        # 构建消息（注入文件引用）
        message = await _build_message_with_files(
            request.message, request.file_ids
        )
        # 记录文件归属
        for fid in request.file_ids:
            if fid not in state.uploaded_file_ids:
                state.uploaded_file_ids.append(fid)

        # 解析配置
        resolved_config = await resolve_config(current_user.id, db)

        async def event_generator():
            """SSE 事件生成器"""
            async for chunk in chat_with_agent_stream(
                message=message,
                state=state,
                db=db,
                resolved_config=resolved_config,
            ):
                event_data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

        # 用 BackgroundTasks 保存 State。
        # 不使用请求级 db session——StreamingResponse 期间 session 生命周期不确定，
        # 这里创建独立 session 确保写入可靠。
        async def _save_after_stream():
            # 先提交请求级 session，释放 SQLite 写锁（工具调用期间 edit_table 已 flush）
            try:
                await db.commit()
            except Exception:
                pass

            async with async_session() as save_db:
                await _save_state(state, save_db)
                await save_db.commit()

        background_tasks.add_task(_save_after_stream)

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
    from backend.provider_config import load_yaml_config
    yaml_config = load_yaml_config()
    defaults = yaml_config.get("defaults", {})
    return {
        "status": "ok",
        "default_provider": defaults.get("provider", "deepseek"),
        "default_model": defaults.get("model", ""),
    }


class ConfigUpdateRequest(BaseModel):
    """配置更新请求（所有字段可选，仅更新传入的字段）"""
    llm_model: str | None = None
    llm_higher_model: str | None = None
    llm_max_tokens: int | None = None
    debug: bool | None = None
    log_level: str | None = None
    scenario_configs: dict | None = None


# 配置字段名 → settings 属性名映射
_CONFIG_FIELD_MAP = {
    "llm_model": "LLM_MODEL",
    "llm_higher_model": "LLM_HIGHER_MODEL",
    "llm_max_tokens": "LLM_MAX_TOKENS",
    "debug": "DEBUG",
    "log_level": "LOG_LEVEL",
    "scenario_configs": "SCENARIO_CONFIGS",
}


@router.get("/config")
async def get_config():
    """获取当前配置（不含敏感字段）"""
    from backend.config import settings
    from backend.provider_config import load_yaml_config, get_all_providers

    yaml_config = load_yaml_config()
    defaults = yaml_config.get("defaults", {})
    providers = get_all_providers()

    return {
        "providers": {p.key: {
            "name": p.name,
            "models": [{"id": m.id, "context_limit": m.context_limit, "description": m.description} for m in p.models],
            "requires_api_key": p.requires_api_key,
        } for p in providers},
        "defaults": {
            "provider": defaults.get("provider", "deepseek"),
            "model": defaults.get("model", ""),
            "higher_model": defaults.get("higher_model", ""),
            "max_tokens": defaults.get("max_tokens"),
            "scenario_configs": defaults.get("scenario_configs", {}),
        },
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
    }


@router.put("/config")
async def update_config(req: ConfigUpdateRequest):
    """更新配置（内存 + config.yaml 文件持久化）"""
    from backend.config import settings
    from backend.provider_config import update_defaults_in_yaml

    updates = {}

    # 更新 YAML 中的 defaults
    yaml_updates = {}
    if req.llm_model is not None:
        yaml_updates["model"] = req.llm_model
    if req.llm_higher_model is not None:
        yaml_updates["higher_model"] = req.llm_higher_model
    if req.llm_max_tokens is not None:
        yaml_updates["max_tokens"] = req.llm_max_tokens
    if req.scenario_configs is not None:
        yaml_updates["scenario_configs"] = req.scenario_configs

    if yaml_updates:
        update_defaults_in_yaml(yaml_updates)
        updates.update(yaml_updates)

    # 更新系统配置（DEBUG、LOG_LEVEL 仍存 .env）
    from backend.config import save_to_env
    env_updates = {}
    if req.debug is not None:
        settings.DEBUG = req.debug
        env_updates["DEBUG"] = req.debug
    if req.log_level is not None:
        settings.LOG_LEVEL = req.log_level
        env_updates["LOG_LEVEL"] = req.log_level
    if env_updates:
        save_to_env(env_updates)

    return {"updated": updates}


# ========== 会话管理 API ==========

class SessionInfo(BaseModel):
    session_id: str
    scenario: str
    title: str = ""
    created_at: str | None
    updated_at: str | None


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]


@router.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    scenario: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的会话列表"""
    sessions = await list_user_sessions(db, current_user.id, scenario)
    return SessionListResponse(sessions=[SessionInfo(**s) for s in sessions])


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除指定会话"""
    success = await delete_session(db, session_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/sessions/{session_id}/load")
async def load_session_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """加载指定会话的完整状态（用于恢复会话）"""
    session_data, loop_data = await load_session(db, session_id)
    if not session_data or session_data.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 合并返回，保持 API 兼容
    merged = {**session_data}
    if loop_data:
        merged.update(loop_data)
    return merged


# ========== 岗位搜索 API ==========

class JobSearchRequest(BaseModel):
    """岗位搜索请求"""
    filters: dict = Field(default_factory=dict, description="筛选条件")


class JobSearchResponse(BaseModel):
    """岗位搜索响应"""
    jobs: list[dict]
    total: int
    summary: str


@router.post("/job-search", response_model=JobSearchResponse)
async def job_search(
    request: JobSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """岗位搜索 + 匹配分析"""
    from backend.services.job_search import search_and_analyze

    result = await search_and_analyze(db, current_user.id, request.filters)
    return JobSearchResponse(**result)


@router.post("/job-search/stream")
async def job_search_stream(
    request: JobSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """岗位搜索 + 匹配分析（流式）"""
    from backend.services.job_search import search_and_analyze_stream

    async def event_generator():
        async for chunk in search_and_analyze_stream(db, current_user.id, request.filters):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
