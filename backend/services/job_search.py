"""岗位搜索与匹配分析服务"""

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.client import create_client_for_config
from backend.models.resume import Resume
from backend.provider_config import resolve_config

logger = logging.getLogger(__name__)

# Mock 数据路径
MOCK_DATA_PATH = Path(__file__).parent.parent / "data" / "mock_jobs.json"


def load_mock_jobs() -> list[dict]:
    """加载 Mock 岗位数据"""
    with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def filter_jobs(jobs: list[dict], filters: dict) -> list[dict]:
    """按条件过滤岗位"""
    result = jobs

    if filters.get("city"):
        result = [j for j in result if j["city"] == filters["city"]]

    if filters.get("job_type"):
        result = [j for j in result if j["job_type"] == filters["job_type"]]

    if filters.get("experience"):
        result = [j for j in result if j["experience"] == filters["experience"]]

    if filters.get("education"):
        result = [j for j in result if j["education"] == filters["education"]]

    if filters.get("company_size"):
        result = [j for j in result if j["company_size"] == filters["company_size"]]

    if filters.get("salary_min"):
        salary_min = filters["salary_min"]
        result = [j for j in result if j["salary_max"] >= salary_min]

    if filters.get("keywords"):
        keywords = filters["keywords"]
        if isinstance(keywords, str):
            keywords = [keywords]
        result = [
            j for j in result
            if any(
                kw.lower() in " ".join(j["tags"]).lower()
                or kw.lower() in j["title"].lower()
                or kw.lower() in j["description"].lower()
                for kw in keywords
            )
        ]

    return result[:20]


async def get_user_resume_data(db: AsyncSession, user_id: int) -> dict | None:
    """获取用户简历数据"""
    result = await db.execute(select(Resume).where(Resume.user_id == user_id))
    resume = result.scalar_one_or_none()

    if not resume or not resume.basic_info:
        return None

    return {
        "basic_info": resume.basic_info,
        "education": resume.education,
        "internship_exp": resume.internship_exp,
        "project_exp": resume.project_exp,
        "personal_strengths": resume.personal_strengths,
    }


async def analyze_matches(
    jobs: list[dict],
    resume_data: dict,
    resolved_config=None,
) -> list[dict]:
    """调用 LLM 分析岗位匹配度"""
    prompt = f"""你是资深求职顾问。根据以下简历和岗位列表，分析每个岗位的匹配度。

简历：
{json.dumps(resume_data, ensure_ascii=False, indent=2)}

岗位列表：
{json.dumps(jobs, ensure_ascii=False, indent=2)}

请为每个岗位输出 JSON 数组，每项包含：
- job_id: 岗位 ID（整数）
- score: 匹配分数（0-100，整数）
- reason: 推荐理由（一句话，不超过30字）

评分标准：
- 技能匹配度（40%）：简历技能与岗位要求的重合度
- 经验匹配度（30%）：工作经验与岗位要求的匹配
- 学历匹配度（15%）：学历是否满足要求
- 综合匹配度（15%）：城市、薪资期望等

只输出 JSON 数组，不要其他内容。"""

    try:
        client = create_client_for_config(resolved_config)
        response = await client.chat.completions.create(
            model=resolved_config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response.choices[0].message.content

        # 提取 JSON 数组
        if "[" in content and "]" in content:
            start = content.index("[")
            end = content.rindex("]") + 1
            json_str = content[start:end]
            return json.loads(json_str)

        return []
    except Exception as e:
        logger.error("LLM 匹配分析失败: %s", e)
        return []


async def generate_summary(
    jobs: list[dict],
    resume_data: dict,
    resolved_config=None,
) -> str:
    """生成筛选建议"""
    prompt = f"""你是求职顾问。根据用户的简历和搜索结果，给出简短的求职建议（3-5句话）。

简历摘要：
- 姓名：{resume_data.get("basic_info", {}).get("name", "未知")}
- 技能：{", ".join(resume_data.get("personal_strengths", {}).get("skills", []))}

搜索到 {len(jobs)} 个岗位。

请给出：
1. 整体匹配情况评价
2. 建议关注的方向
3. 提升竞争力的建议

简短回答即可。"""

    try:
        client = create_client_for_config(resolved_config)
        response = await client.chat.completions.create(
            model=resolved_config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=300,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("生成建议失败: %s", e)
        return "暂无筛选建议"


async def search_and_analyze(
    db: AsyncSession,
    user_id: int,
    filters: dict,
) -> dict:
    """搜索岗位并分析匹配度"""
    # 1. 加载并过滤 Mock 数据
    all_jobs = load_mock_jobs()
    filtered_jobs = filter_jobs(all_jobs, filters)

    if not filtered_jobs:
        return {
            "jobs": [],
            "total": 0,
            "summary": "未找到符合条件的岗位，请调整筛选条件",
        }

    # 2. 获取用户简历
    resume_data = await get_user_resume_data(db, user_id)

    if not resume_data:
        # 无简历时返回岗位列表（无匹配分析）
        return {
            "jobs": [
                {
                    **job,
                    "score": 0,
                    "reason": "请先完善简历以获取匹配分析",
                }
                for job in filtered_jobs
            ],
            "total": len(filtered_jobs),
            "summary": "您尚未完善简历，建议先填写简历以获取精准推荐",
        }

    # 3. 解析 LLM 配置
    resolved_config = await resolve_config(user_id, db)

    # 4. LLM 匹配分析
    matches = await analyze_matches(filtered_jobs, resume_data, resolved_config)

    # 5. 合并结果
    match_map = {m["job_id"]: m for m in matches}
    enriched_jobs = []
    for job in filtered_jobs:
        match_info = match_map.get(job["id"], {})
        enriched_jobs.append({
            **job,
            "score": match_info.get("score", 50),
            "reason": match_info.get("reason", "暂无推荐理由"),
        })

    # 按匹配分数排序
    enriched_jobs.sort(key=lambda x: x["score"], reverse=True)

    # 6. 生成筛选建议
    summary = await generate_summary(enriched_jobs[:5], resume_data, resolved_config)

    return {
        "jobs": enriched_jobs,
        "total": len(enriched_jobs),
        "summary": summary,
    }


async def search_and_analyze_stream(
    db: AsyncSession,
    user_id: int,
    filters: dict,
):
    """流式搜索岗位并分析匹配度"""
    # 1. 加载并过滤 Mock 数据
    all_jobs = load_mock_jobs()
    filtered_jobs = filter_jobs(all_jobs, filters)

    if not filtered_jobs:
        yield {"type": "jobs", "data": []}
        yield {"type": "summary", "data": "未找到符合条件的岗位，请调整筛选条件"}
        return

    # 2. 先返回岗位列表（无匹配分数）
    yield {
        "type": "jobs",
        "data": [
            {**job, "score": 0, "reason": "分析中..."}
            for job in filtered_jobs
        ],
    }

    # 3. 获取用户简历
    resume_data = await get_user_resume_data(db, user_id)

    if not resume_data:
        yield {"type": "summary", "data": "您尚未完善简历，建议先填写简历以获取精准推荐"}
        return

    # 4. 解析 LLM 配置
    resolved_config = await resolve_config(user_id, db)

    # 5. LLM 匹配分析
    matches = await analyze_matches(filtered_jobs, resume_data, resolved_config)

    # 6. 逐条返回匹配结果
    match_map = {m["job_id"]: m for m in matches}
    for job in filtered_jobs:
        match_info = match_map.get(job["id"], {})
        yield {
            "type": "analysis",
            "data": {
                "job_id": job["id"],
                "score": match_info.get("score", 50),
                "reason": match_info.get("reason", "暂无推荐理由"),
            },
        }

    # 7. 生成筛选建议
    summary = await generate_summary(filtered_jobs[:5], resume_data, resolved_config)
    yield {"type": "summary", "data": summary}
