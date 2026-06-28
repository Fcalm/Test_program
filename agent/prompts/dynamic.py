"""各 work 场景的动态提示词模板

从 State 的 tool_results 中提取数据，构建动态提示词。
"""

from typing import Any


# 动态提示词模板
DYNAMIC_TEMPLATES = {
    "resume": """## 简历与 JD 状态:
{resume_status}
{jd_status}""",

    "interview": """## 当前面试状态:
- 面试轮次：第 {round} 轮 / 共2轮
"""
}


def build_dynamic_prompt(work: str, context: dict[str, Any]) -> str:
    """
    构建动态提示词

    从 context 中读取 tool_results 和 stage，提取所需数据。

    Args:
        work: 当前 work 类型
        context: 动态上下文数据（包含 tool_results、stage 等）

    Returns:
        格式化后的动态提示词
    """
    template = DYNAMIC_TEMPLATES.get(work, "")
    if not template:
        return ""

    # 从 tool_results 中提取数据
    tool_results = context.get("tool_results", {})
    resume_data = _extract_resume_data(tool_results)
    jd_data = _extract_jd_data(tool_results)

    # 构建状态描述
    resume_status = _build_resume_status(resume_data)
    jd_status = _build_jd_status(jd_data)

    # 根据 work 类型填充模板
    if work == "resume":
        return template.format(
            resume_status=resume_status,
            jd_status=jd_status,
        )
    elif work == "interview":
        return template.format(
            round=context.get("round", 1)
        )
    else:
        return ""


def _extract_resume_data(tool_results: dict) -> dict | None:
    """从 tool_results 中提取简历数据"""
    # 尝试从 parse_resume 工具结果中获取
    parse_result = tool_results.get("parse_resume")
    if parse_result and isinstance(parse_result, dict):
        if parse_result.get("success") and "basic_info" in parse_result:
            return parse_result

    # 尝试从 get_resume_table 工具结果中获取
    get_result = tool_results.get("get_resume_table")
    if get_result and isinstance(get_result, dict):
        if get_result.get("success") and "basic_info" in get_result:
            return get_result

    return None


def _extract_jd_data(tool_results: dict) -> dict | None:
    """从 tool_results 中提取 JD 数据"""
    parse_result = tool_results.get("parse_jd")
    if parse_result and isinstance(parse_result, dict):
        if parse_result.get("success"):
            return parse_result

    return None


def _build_resume_status(resume_data: dict | None) -> str:
    """构建简历状态描述"""
    if not resume_data:
        return "简历状态：用户尚未提供简历数据"

    basic_info = resume_data.get("basic_info", {})
    name = basic_info.get("name", "未知")

    education = resume_data.get("education", [])
    school = education[0].get("school", "未知") if education else "未知"

    internship_count = len(resume_data.get("internship_exp", []))
    project_count = len(resume_data.get("project_exp", []))

    return f"""简历状态：已有简历数据
- 姓名：{name}
- 学校：{school}
- 实习经历：{internship_count} 段
- 项目经历：{project_count} 个"""


def _build_jd_status(jd_data: dict | None) -> str:
    """构建 JD 状态描述"""
    if not jd_data:
        return "没有可用的 JD 数据"

    company = jd_data.get("company", "未知")
    position = jd_data.get("position", "未知")
    skills = jd_data.get("key_skills", [])
    skills_str = "、".join(skills[:5]) if skills else "无"

    return f"""

JD 状态：已解析 JD 数据
- 公司：{company}
- 岗位：{position}
- 核心技能：{skills_str}"""
