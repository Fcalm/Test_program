import asyncio
import json
import re

import httpx
from bs4 import BeautifulSoup
from jsonschema import validate, ValidationError

from backend.schemas.jd import JDParsed, JDParseResponse

# 请求超时（秒）
REQUEST_TIMEOUT = 15

# 请求头（模拟浏览器）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _extract_nuxt_jd(html: str) -> tuple[str, dict] | None:
    """从 Nuxt SSR 页面的 window.__NUXT__ 中提取 JD 文本和元数据

    Returns: (jd_text, metadata) 或 None
    """
    m = re.search(r'o\.info="((?:[^"\\]|\\.)*)"', html)
    if not m:
        return None
    text = m.group(1).replace("\\n", "\n").replace("\\u002F", "/")
    if len(text) < 20:
        return None

    # 提取结构化字段
    def _field(pattern: str) -> str:
        fm = re.search(pattern, html)
        return fm.group(1).replace("\\u002F", "/") if fm else ""

    meta = {
        "position": _field(r'o\.iname="((?:[^"\\]|\\.)*)"'),
        "company": _field(r'o\.cname="((?:[^"\\]|\\.)*)"'),
        "salary": _field(r'o\.salary_desc="((?:[^"\\]|\\.)*)"'),
        "location": _field(r'o\.address="((?:[^"\\]|\\.)*)"'),
    }
    return text, meta


def _fetch_url_content(url: str) -> tuple[str, dict]:
    """从 URL 抓取网页正文内容，返回 (正文文本, 元数据)"""
    resp = httpx.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()

    html = resp.text

    # 优先从结构化数据中提取（Nuxt SSR / JSON-LD / meta description）
    nuxt_result = _extract_nuxt_jd(html)
    if nuxt_result:
        return nuxt_result

    # JSON-LD 结构化数据
    m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            import json as _json
            ld = _json.loads(m.group(1))
            desc = ld.get("description", "")
            if desc and len(desc) > 20:
                return desc, {}
        except Exception:
            pass

    # 兜底：BeautifulSoup 提取正文
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    main = soup.find("article") or soup.find("main") or soup.find("body")
    if not main:
        raise ValueError("无法提取网页正文内容")

    text = main.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines), {}


# JD JSON Schema 校验规则
JD_SCHEMA = {
    "type": "object",
    "properties": {
        "position": {"type": "string"},
        "company": {"type": "string"},
        "responsibilities": {"type": "array", "items": {"type": "string"}},
        "requirements": {"type": "array", "items": {"type": "string"}},
        "salary": {"type": "string"},
        "location": {"type": "string"},
        "benefits": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["position"],
}

# 超时时间（秒）
TIMEOUT_SECONDS = 30

# JD 关键词（用于前端检测）
JD_KEYWORDS = ["岗位", "职位", "职责", "要求", "任职", "薪资", "福利", "工作内容", "任职资格", "岗位描述"]


def _extract_by_regex(text: str) -> dict | None:
    """正则提取 JD 各字段"""
    result = {
        "position": "",
        "company": "",
        "responsibilities": [],
        "requirements": [],
        "salary": "",
        "location": "",
        "benefits": [],
    }

    # 提取职位名称（通常在标题行或"职位："后面）
    pos_patterns = [
        r"职位[：:]\s*(.+?)(?:\n|$)",
        r"岗位[：:]\s*(.+?)(?:\n|$)",
        r"招聘[：:]\s*(.+?)(?:\n|$)",
        r"^#\s*(.+?)(?:\n|$)",  # Markdown 标题
    ]
    for p in pos_patterns:
        m = re.search(p, text, re.MULTILINE)
        if m:
            result["position"] = m.group(1).strip().rstrip("【】[]")
            break

    # 如果没有明确的职位字段，尝试从第一行提取
    if not result["position"]:
        first_line = text.strip().split("\n")[0].strip()
        if len(first_line) < 30:
            result["position"] = first_line

    # 提取公司名称
    comp_patterns = [
        r"公司[：:]\s*(.+?)(?:\n|$)",
        r"企业[：:]\s*(.+?)(?:\n|$)",
        r"单位[：:]\s*(.+?)(?:\n|$)",
    ]
    for p in comp_patterns:
        m = re.search(p, text)
        if m:
            result["company"] = m.group(1).strip()
            break

    # 提取薪资
    salary_patterns = [
        r"薪[资酬][：:]\s*(.+?)(?:\n|$)",
        r"(\d+[kK]\s*[-~至]\s*\d+[kK])",
        r"(\d+\s*[-~至]\s*\d+\s*[万Ww])",
    ]
    for p in salary_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            result["salary"] = m.group(1).strip()
            break

    # 提取工作地点
    loc_patterns = [
        r"地[点址][：:]\s*(.+?)(?:\n|$)",
        r"工作地[点址][：:]\s*(.+?)(?:\n|$)",
        r"城市[：:]\s*(.+?)(?:\n|$)",
    ]
    for p in loc_patterns:
        m = re.search(p, text)
        if m:
            result["location"] = m.group(1).strip()
            break

    # 提取岗位职责
    resp_section = _extract_list_section(text, ["岗位职责", "工作职责", "职责描述", "工作内容", "职位描述"])
    if resp_section:
        result["responsibilities"] = resp_section

    # 提取任职要求
    req_section = _extract_list_section(text, ["任职要求", "岗位要求", "职位要求", "任职资格", "基本要求", "能力要求"])
    if req_section:
        result["requirements"] = req_section

    # 提取福利待遇
    ben_section = _extract_list_section(text, ["福利待遇", "薪资福利", "福利", "我们提供"])
    if ben_section:
        result["benefits"] = ben_section

    # 检查是否提取到了有效内容
    if not result["position"] and not result["responsibilities"] and not result["requirements"]:
        return None

    return result


def _extract_list_section(text: str, headers: list[str]) -> list[str]:
    """从文本中提取某个章节下的列表项"""
    for header in headers:
        # 找到标题位置
        idx = text.find(header)
        if idx == -1:
            continue

        # 从标题后开始截取（跳过标题行和冒号）
        start = idx + len(header)
        while start < len(text) and text[start] in "：: \t":
            start += 1

        remaining = text[start:]

        # 找下一个章节标题（中文标题 + 冒号，如"任职要求："）
        next_section = re.search(r"\n\s*[一-龥]{2,8}[：:]", remaining)
        end = next_section.start() if next_section else len(remaining)

        section = remaining[:end].strip()

        # 提取列表项（支持 1. 2. / - / • 等格式）
        items = re.findall(r"(?:^|\n)\s*(?:[-•·*]|\d+[、.)\]]?)\s*(.+)", section)
        if items:
            return [item.strip() for item in items if item.strip()]

        # 没有列表标记，按行分割
        lines = [line.strip() for line in section.split("\n") if line.strip()]
        if lines:
            return lines
    return []


def _validate_schema(data: dict) -> bool:
    """JSON Schema 校验"""
    try:
        validate(instance=data, schema=JD_SCHEMA)
        return True
    except ValidationError:
        return False


async def _llm_parse(text: str) -> dict | None:
    """LLM 兜底解析（模拟，后续接入真实 LLM）"""
    # TODO: 接入真实 LLM API
    # 这里用简单的启发式方法作为兜底
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    result = {
        "position": "",
        "company": "",
        "responsibilities": [],
        "requirements": [],
        "salary": "",
        "location": "",
        "benefits": [],
    }

    # 尝试从第一行提取职位
    if lines:
        result["position"] = lines[0][:50]

    # 按行归类（简单启发式）
    current_section = "responsibilities"
    for line in lines[1:]:
        if any(kw in line for kw in ["要求", "资格", "学历"]):
            current_section = "requirements"
        elif any(kw in line for kw in ["福利", "待遇", "薪资"]):
            current_section = "benefits"
        elif len(line) > 5 and not line.startswith(("公司", "地点", "薪资")):
            result[current_section].append(line)

    if not result["position"] and not result["responsibilities"]:
        return None

    return result


async def parse_jd(text: str) -> JDParseResponse:
    """解析 JD 文本，带超时控制"""
    try:
        # 第一步：正则提取
        result = await asyncio.wait_for(
            asyncio.to_thread(_extract_by_regex, text),
            timeout=TIMEOUT_SECONDS,
        )

        if result and _validate_schema(result):
            return JDParseResponse(
                success=True,
                data=JDParsed(**result),
                method="regex",
            )

        # 第二步：LLM 兜底
        result = await asyncio.wait_for(
            _llm_parse(text),
            timeout=TIMEOUT_SECONDS,
        )

        if result and _validate_schema(result):
            return JDParseResponse(
                success=True,
                data=JDParsed(**result),
                method="llm",
            )

        return JDParseResponse(
            success=False,
            error="无法解析 JD 内容，请检查文本格式",
        )

    except asyncio.TimeoutError:
        return JDParseResponse(
            success=False,
            error=f"解析超时（{TIMEOUT_SECONDS}秒），请稍后重试",
        )
    except Exception as e:
        return JDParseResponse(
            success=False,
            error=f"解析异常：{str(e)}",
        )


async def parse_jd_from_url(url: str) -> JDParseResponse:
    """从 URL 抓取并解析 JD"""
    try:
        # 抓取网页内容和元数据
        text, meta = await asyncio.wait_for(
            asyncio.to_thread(_fetch_url_content, url),
            timeout=REQUEST_TIMEOUT,
        )

        if not text or len(text) < 20:
            return JDParseResponse(
                success=False,
                error="网页内容过少，无法解析为 JD",
            )

        # 调用已有的文本解析逻辑
        result = await parse_jd(text)

        # 用结构化元数据补全正则解析缺失或明显错误的字段
        if result.success and meta:
            data = result.data
            # position 若是章节标题（如"岗位职责："）则用元数据覆盖
            if meta.get("position"):
                if not data.position or data.position.endswith(("：", ":", "职责", "要求")):
                    data.position = meta["position"]
            if not data.company and meta.get("company"):
                data.company = meta["company"]
            if not data.salary and meta.get("salary"):
                data.salary = meta["salary"]
            if not data.location and meta.get("location"):
                data.location = meta["location"]

        return result

    except httpx.TimeoutException:
        return JDParseResponse(
            success=False,
            error=f"网页请求超时（{REQUEST_TIMEOUT}秒），请检查 URL 或稍后重试",
        )
    except httpx.HTTPStatusError as e:
        return JDParseResponse(
            success=False,
            error=f"网页请求失败（HTTP {e.response.status_code}）",
        )
    except Exception as e:
        return JDParseResponse(
            success=False,
            error=f"URL 解析异常：{str(e)}",
        )
