"""Agent 工具辅助函数"""


def _format_jd_info(data: dict) -> str:
    """格式化 JD 数据为可读文本"""
    parts = []

    position = data.get("position", "")
    company = data.get("company", "")
    if position:
        parts.append(f"岗位：{position}")
    if company:
        parts.append(f"公司：{company}")

    salary = data.get("salary", "")
    location = data.get("location", "")
    if salary:
        parts.append(f"薪资：{salary}")
    if location:
        parts.append(f"地点：{location}")

    responsibilities = data.get("responsibilities", [])
    if responsibilities:
        parts.append("岗位职责：")
        for item in responsibilities[:5]:
            parts.append(f"  - {item}")

    requirements = data.get("requirements", [])
    if requirements:
        parts.append("任职要求：")
        for item in requirements[:5]:
            parts.append(f"  - {item}")

    return "\n".join(parts)
