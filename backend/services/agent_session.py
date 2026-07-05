"""Agent 会话状态服务

双表存储：
- agent_sessions: 会话恢复数据（messages, key_data, summary 等）
- agent_loop_state: 引擎连续性数据（usage, summary_token_checkpoint）

Redis 缓存层保留，读写策略不变。
"""

import json
import logging

logger = logging.getLogger(__name__)

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_session import AgentSession
from backend.models.agent_loop_state import AgentLoopState
from backend.services.agent_cache import (
    get_session_state as redis_get_session,
    save_session_state as redis_save_session,
    delete_session_state as redis_delete_session,
)

# 每用户每场景最大会话数
MAX_SESSIONS_PER_SCENARIO = 10


async def _cleanup_old_sessions(db: AsyncSession, user_id: int, scenario: str) -> None:
    """清理用户在指定场景下超出上限的旧会话"""
    count_result = await db.execute(
        select(func.count()).where(
            AgentSession.user_id == user_id,
            AgentSession.scenario == scenario,
        )
    )
    total = count_result.scalar() or 0

    if total <= MAX_SESSIONS_PER_SCENARIO:
        return

    excess = total - MAX_SESSIONS_PER_SCENARIO
    old_sessions = await db.execute(
        select(AgentSession)
        .where(
            AgentSession.user_id == user_id,
            AgentSession.scenario == scenario,
        )
        .order_by(AgentSession.updated_at.asc())
        .limit(excess)
    )
    for s in old_sessions.scalars().all():
        await db.delete(s)


async def load_session(db: AsyncSession, session_id: str) -> tuple[dict | None, dict | None]:
    """从数据库加载会话状态（带 Redis 缓存）

    Returns:
        (session_data, loop_data) 元组，不存在返回 (None, None)
    """
    # 1. 优先尝试 Redis
    try:
        cached = await redis_get_session(session_id)
        if cached:
            state = cached.get("state", {})
            session_data = {
                "session_id": session_id,
                "user_id": state.get("user_id"),
                "scenario": state.get("scenario", ""),
                "title": state.get("title", ""),
                "messages": cached.get("messages", []),
                "key_data": cached.get("tool_cache", {}),
                "uploaded_file_ids": state.get("uploaded_file_ids", []),
                "summary": state.get("summary", ""),
            }
            loop_data = {
                "session_id": session_id,
                "usage": state.get("usage", {}),
                "summary_token_checkpoint": state.get("summary_token_checkpoint", 0),
                "summary_update_count": state.get("summary_update_count", 0),
            }
            return session_data, loop_data
    except Exception:
        pass

    # 2. 降级到 SQLite — 读 agent_sessions
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        return None, None

    session_data = {
        "session_id": session.id,
        "user_id": session.user_id,
        "scenario": session.scenario,
        "title": session.title or "",
        "messages": json.loads(session.messages) if session.messages else [],
        "key_data": json.loads(session.key_data) if session.key_data else {},
        "uploaded_file_ids": json.loads(session.uploaded_file_ids) if session.uploaded_file_ids else [],
        "summary": session.summary or "",
    }

    # 3. 读 agent_loop_state
    loop_result = await db.execute(
        select(AgentLoopState).where(AgentLoopState.session_id == session_id)
    )
    loop_row = loop_result.scalar_one_or_none()

    loop_data = {
        "session_id": session_id,
        "usage": json.loads(loop_row.usage) if loop_row and loop_row.usage else {},
        "summary_token_checkpoint": loop_row.summary_token_checkpoint if loop_row else 0,
        "summary_update_count": loop_row.summary_update_count if loop_row else 0,
    }

    # 4. 回填 Redis
    try:
        merged = {**session_data, **loop_data}
        await redis_save_session(
            session_id=session_id,
            user_id=session.user_id,
            state=merged,
            messages=session_data["messages"],
            tool_cache=session_data["key_data"],
        )
    except Exception:
        pass

    return session_data, loop_data


async def save_session(
    db: AsyncSession,
    session_data: dict,
    loop_data: dict | None = None,
) -> None:
    """保存会话状态到数据库

    Args:
        db: 数据库会话
        session_data: AgentState.snapshot_session() 返回的字典
        loop_data: AgentState.snapshot_loop() 返回的字典（可选）
    """
    session_id = session_data["session_id"]
    user_id = session_data["user_id"]
    logger.info("save_session 开始: session_id=%s, user_id=%s", session_id, user_id)

    # 1. 同步写入 Redis
    try:
        merged = {**session_data}
        if loop_data:
            merged.update(loop_data)
        await redis_save_session(
            session_id=session_id,
            user_id=user_id,
            state=merged,
            messages=session_data.get("messages", []),
            tool_cache=session_data.get("key_data", {}),
        )
        logger.info("Redis 写入成功: session_id=%s", session_id)
    except Exception as e:
        logger.warning("Redis 写入失败（降级到 SQLite）: %s", e)

    # 2. 写入 agent_sessions
    try:
        result = await db.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.scenario = session_data.get("scenario", "")
            existing.title = session_data.get("title", "")
            existing.messages = json.dumps(session_data.get("messages", []), ensure_ascii=False)
            existing.key_data = json.dumps(session_data.get("key_data", {}), ensure_ascii=False)
            existing.uploaded_file_ids = json.dumps(session_data.get("uploaded_file_ids", []), ensure_ascii=False)
            existing.summary = session_data.get("summary", "")
            logger.info("SQLite 更新现有 agent_sessions: session_id=%s", session_id)
        else:
            new_session = AgentSession(
                id=session_id,
                user_id=user_id,
                scenario=session_data.get("scenario", ""),
                title=session_data.get("title", ""),
                messages=json.dumps(session_data.get("messages", []), ensure_ascii=False),
                key_data=json.dumps(session_data.get("key_data", {}), ensure_ascii=False),
                uploaded_file_ids=json.dumps(session_data.get("uploaded_file_ids", []), ensure_ascii=False),
                summary=session_data.get("summary", ""),
            )
            db.add(new_session)
            logger.info("SQLite INSERT 新 agent_sessions: session_id=%s", session_id)

        await db.flush()

        # 清理旧会话
        await _cleanup_old_sessions(db, user_id, session_data.get("scenario", ""))
    except Exception as e:
        logger.error("SQLite agent_sessions 写入失败: session_id=%s, error=%s", session_id, e)
        raise

    # 3. 写入 agent_loop_state
    if loop_data:
        try:
            loop_result = await db.execute(
                select(AgentLoopState).where(AgentLoopState.session_id == session_id)
            )
            existing_loop = loop_result.scalar_one_or_none()

            if existing_loop:
                existing_loop.usage = json.dumps(loop_data.get("usage", {}), ensure_ascii=False)
                existing_loop.summary_token_checkpoint = loop_data.get("summary_token_checkpoint", 0)
                existing_loop.summary_update_count = loop_data.get("summary_update_count", 0)
                logger.info("SQLite 更新现有 agent_loop_state: session_id=%s", session_id)
            else:
                new_loop = AgentLoopState(
                    session_id=session_id,
                    usage=json.dumps(loop_data.get("usage", {}), ensure_ascii=False),
                    summary_token_checkpoint=loop_data.get("summary_token_checkpoint", 0),
                    summary_update_count=loop_data.get("summary_update_count", 0),
                )
                db.add(new_loop)
                logger.info("SQLite INSERT 新 agent_loop_state: session_id=%s", session_id)

            await db.flush()
        except Exception as e:
            logger.error("SQLite agent_loop_state 写入失败: session_id=%s, error=%s", session_id, e)
            raise


async def list_user_sessions(
    db: AsyncSession,
    user_id: int,
    scenario: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """获取用户的会话列表"""
    query = (
        select(AgentSession)
        .where(AgentSession.user_id == user_id)
        .order_by(AgentSession.updated_at.desc())
        .limit(limit)
    )

    if scenario:
        query = query.where(AgentSession.scenario == scenario)

    result = await db.execute(query)
    sessions = result.scalars().all()

    return [
        {
            "session_id": s.id,
            "scenario": s.scenario,
            "title": s.title or "",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]


async def delete_session(db: AsyncSession, session_id: str, user_id: int) -> bool:
    """删除会话（含 agent_loop_state + 分析会话 + Redis 缓存清理）"""
    result = await db.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        return False

    # 删除 agent_loop_state
    loop_result = await db.execute(
        select(AgentLoopState).where(AgentLoopState.session_id == session_id)
    )
    loop_row = loop_result.scalar_one_or_none()
    if loop_row:
        await db.delete(loop_row)

    # 删除绑定的分析会话
    analysis_session_id = f"{session_id}-analysis"
    analysis_result = await db.execute(
        select(AgentSession).where(AgentSession.id == analysis_session_id)
    )
    analysis_session = analysis_result.scalar_one_or_none()
    if analysis_session:
        await db.delete(analysis_session)

    # 删除主会话
    await db.delete(session)
    await db.flush()

    # 清理 Redis 缓存
    try:
        await redis_delete_session(session_id, user_id)
    except Exception:
        pass
    try:
        await redis_delete_session(analysis_session_id, user_id)
    except Exception:
        pass

    return True
