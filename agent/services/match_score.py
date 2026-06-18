"""JD 与简历匹配分数计算"""


def calculate_match_score(jd_data: dict, resume_data: dict) -> dict:
    """
    计算 JD 与简历的匹配分数

    Args:
        jd_data: JD 解析数据
        resume_data: 简历数据

    Returns:
        匹配分数结果字典
    """
    # 提取 JD 关键词
    jd_keywords = set()
    for req in jd_data.get("requirements", []):
        jd_keywords.update(_extract_keywords(req))
    for resp in jd_data.get("responsibilities", []):
        jd_keywords.update(_extract_keywords(resp))

    # 提取简历关键词
    resume_keywords = set()
    for exp in resume_data.get("internship_exp", []):
        for desc in exp.get("description", []):
            resume_keywords.update(_extract_keywords(desc))
    for proj in resume_data.get("project_exp", []):
        for desc in proj.get("description", []):
            resume_keywords.update(_extract_keywords(desc))
    for strength in resume_data.get("personal_strengths", []):
        resume_keywords.update(_extract_keywords(strength))

    # 计算匹配
    matched = jd_keywords & resume_keywords
    missing = jd_keywords - resume_keywords

    # 技能匹配（40分）
    skill_score = min(40, len(matched) * 8) if jd_keywords else 20

    # 经验匹配（30分）- 简化计算
    intern_count = len(resume_data.get("internship_exp", []))
    project_count = len(resume_data.get("project_exp", []))
    experience_score = min(30, intern_count * 10 + project_count * 5)

    # 学历匹配（15分）- 简化
    education_score = 12

    # 关键词匹配（15分）
    keyword_score = min(15, len(matched) * 3) if jd_keywords else 8

    total_score = skill_score + experience_score + education_score + keyword_score

    # 生成建议
    suggestions = []
    if missing:
        suggestions.append(f"建议在简历中补充以下关键词：{', '.join(list(missing)[:5])}")
    if intern_count == 0:
        suggestions.append("建议补充实习经历")
    if project_count < 2:
        suggestions.append("建议补充 2-3 个项目经历")

    return {
        "total_score": total_score,
        "skill_score": skill_score,
        "experience_score": experience_score,
        "education_score": education_score,
        "keyword_score": keyword_score,
        "matched_keywords": list(matched)[:10],
        "missing_keywords": list(missing)[:10],
        "suggestions": suggestions,
    }


def _extract_keywords(text: str) -> set[str]:
    """从文本中提取关键词（简化版）"""
    import re

    # 常见技术关键词
    tech_keywords = {
        "python", "java", "javascript", "typescript", "go", "rust", "c++",
        "react", "vue", "angular", "node", "express", "fastapi", "django",
        "sql", "mysql", "postgresql", "mongodb", "redis",
        "docker", "kubernetes", "aws", "azure", "gcp",
        "机器学习", "深度学习", "nlp", "cv", "数据分析",
        "产品", "运营", "市场", "用户增长", "竞品分析",
        "项目管理", "敏捷", "scrum",
    }

    text_lower = text.lower()
    found = set()

    for kw in tech_keywords:
        if kw in text_lower:
            found.add(kw)

    # 提取英文单词
    words = re.findall(r'[a-zA-Z]+', text)
    for word in words:
        if len(word) > 2:
            found.add(word.lower())

    return found
