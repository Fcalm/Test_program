"""面试分析报告业务逻辑"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis_report import AnalysisReport


async def create_report(
    db: AsyncSession,
    user_id: int,
    session_id: str,
    report_data: dict,
) -> AnalysisReport:
    """创建分析报告"""
    report = AnalysisReport(
        user_id=user_id,
        session_id=session_id,
        report_data=report_data,
        status=report_data.get("status", "in_progress"),
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


async def get_report_by_session(
    db: AsyncSession,
    session_id: str,
) -> AnalysisReport | None:
    """按会话ID获取分析报告"""
    result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def merge_report_data(
    db: AsyncSession,
    user_id: int,
    session_id: str,
    new_data: dict,
) -> AnalysisReport:
    """合并新的分析数据到现有报告

    支持增量更新：
    - rounds: 按 round 编号 upsert（同轮次替换，新轮次追加）
    - final_summary: 整体替换
    - status: 更新状态
    - 其他字段: 深度合并到 report_data
    """
    existing = await get_report_by_session(db, session_id)

    if existing:
        report = existing.report_data or {}

        # 合并 rounds（按 round 编号 upsert）
        if "rounds" in new_data:
            existing_rounds = report.get("rounds", [])
            for new_round in new_data["rounds"]:
                round_num = new_round.get("round")
                existing_rounds = [
                    r for r in existing_rounds if r.get("round") != round_num
                ] + [new_round]
            report["rounds"] = existing_rounds

        # 合并 final_summary（整体替换）
        if "final_summary" in new_data:
            report["final_summary"] = new_data["final_summary"]

        # 更新 status
        if "status" in new_data:
            report["status"] = new_data["status"]

        # 合并其他顶层字段
        for key, value in new_data.items():
            if key not in ("rounds", "final_summary", "status"):
                report[key] = value

        # 写回数据库
        existing.report_data = report
        existing.status = report.get("status", existing.status)
        existing.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(existing)
        return existing
    else:
        # 新建报告
        return await create_report(db, user_id, session_id, new_data)
