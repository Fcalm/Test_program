"""Memory 工具 - 管理持久化记忆（Memory.md）

参考 Hermes 的记忆系统设计，支持子字符串匹配的 add/replace/remove 操作。
"""

import json
import logging
from pathlib import Path

from agent.tools.basetool import BaseTool
from agent.tools.registry import registry

logger = logging.getLogger(__name__)

# Memory.md 文件路径
MEMORY_MD_PATH = Path(__file__).parent.parent / "Memory.md"

# 字符上限
MEMORY_CHAR_LIMIT = 2200

# 类别定义
CATEGORIES = ["用户偏好", "工作习惯", "项目约定", "关键教训"]


def read_memory() -> str:
    """读取 Memory.md 内容"""
    try:
        if MEMORY_MD_PATH.exists():
            return MEMORY_MD_PATH.read_text(encoding="utf-8")
        return ""
    except Exception as e:
        logger.warning("Memory.md 读取失败: %s", e)
        return ""


def write_memory(content: str) -> bool:
    """写入 Memory.md 内容"""
    try:
        MEMORY_MD_PATH.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        logger.error("Memory.md 写入失败: %s", e)
        return False


def parse_memory_sections(content: str) -> dict[str, list[str]]:
    """解析 Memory.md 为类别 -> 条目列表的字典"""
    sections: dict[str, list[str]] = {}
    current_category = None

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 检查是否是类别标题
        if line.startswith("## "):
            category_name = line[3:].strip()
            if category_name in CATEGORIES:
                current_category = category_name
                if current_category not in sections:
                    sections[current_category] = []
            else:
                current_category = None
            continue

        # 收集条目（非空行）
        if current_category and line:
            # 跳过分隔符
            if line == "---":
                continue
            sections[current_category].append(line)

    return sections


def build_memory_content(sections: dict[str, list[str]]) -> str:
    """从类别 -> 条目列表构建 Memory.md 内容"""
    lines = []
    for category in CATEGORIES:
        lines.append(f"## {category}")
        entries = sections.get(category, [])
        if entries:
            for entry in entries:
                lines.append(f"- {entry}")
        lines.append("")  # 空行分隔
    return "\n".join(lines)


def get_memory_usage(content: str) -> tuple[int, float]:
    """获取 Memory.md 的字符使用情况"""
    # 只计算实际内容（去掉标题和格式）
    sections = parse_memory_sections(content)
    actual_chars = sum(
        len(entry)
        for entries in sections.values()
        for entry in entries
    )
    usage_percent = actual_chars / MEMORY_CHAR_LIMIT * 100
    return actual_chars, usage_percent


def find_matching_entries(entries: list[str], old_text: str) -> list[tuple[int, str]]:
    """查找包含子字符串的条目，返回 (index, entry) 列表"""
    matches = []
    for i, entry in enumerate(entries):
        if old_text in entry:
            matches.append((i, entry))
    return matches


class MemoryTool(BaseTool):
    """管理持久化记忆（Memory.md）

    支持 add/replace/remove 操作，使用子字符串匹配（参考 Hermes 设计）。
    """

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "管理持久化记忆（Memory.md）。用于记录用户偏好、工作习惯、项目约定、关键教训，"
            "这些信息会跨会话保持。\n"
            "操作类型：\n"
            "- add: 添加新记忆条目\n"
            "- replace: 替换现有条目（通过子字符串匹配）\n"
            "- remove: 删除条目（通过子字符串匹配）"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "replace", "remove"],
                    "description": "操作类型"
                },
                "target": {
                    "type": "string",
                    "enum": CATEGORIES,
                    "description": "目标类别：用户偏好 | 工作习惯 | 项目约定 | 关键教训"
                },
                "content": {
                    "type": "string",
                    "description": "记忆内容（add/replace 时必填）"
                },
                "old_text": {
                    "type": "string",
                    "description": "要替换/删除的子字符串（replace/remove 时必填，只需是能唯一标识条目的子字符串）"
                }
            },
            "required": ["action", "target"]
        }

    @property
    def max_results_chars(self) -> int:
        return 1000

    @property
    def scenarios(self) -> list[str]:
        return []  # 通用，所有场景可用

    async def execute(self, action: str, target: str, content: str = "", old_text: str = "", **kwargs) -> str:
        """执行记忆操作"""
        logger.debug("调用工具: %s, action=%s, target=%s", self.name, action, target)

        # 验证类别
        if target not in CATEGORIES:
            return json.dumps(
                {"success": False, "error": f"无效类别: {target}，可选: {', '.join(CATEGORIES)}"},
                ensure_ascii=False,
            )

        # 读取当前记忆
        memory_content = read_memory()
        sections = parse_memory_sections(memory_content)

        # 确保类别存在
        if target not in sections:
            sections[target] = []

        # 执行操作
        if action == "add":
            return self._add(sections, target, content)
        elif action == "replace":
            return self._replace(sections, target, old_text, content)
        elif action == "remove":
            return self._remove(sections, target, old_text)
        else:
            return json.dumps(
                {"success": False, "error": f"未知操作: {action}，可选: add, replace, remove"},
                ensure_ascii=False,
            )

    def _add(self, sections: dict[str, list[str]], target: str, content: str) -> str:
        """添加新条目"""
        if not content:
            return json.dumps(
                {"success": False, "error": "添加记忆需要 content 参数"},
                ensure_ascii=False,
            )

        # 检查重复
        for entry in sections.get(target, []):
            if content.strip() == entry.strip():
                return json.dumps(
                    {"success": True, "message": "未添加重复项", "duplicate": True},
                    ensure_ascii=False,
                )

        # 检查容量
        current_content = build_memory_content(sections)
        current_chars, _ = get_memory_usage(current_content)
        new_entry_chars = len(content.strip())

        if current_chars + new_entry_chars > MEMORY_CHAR_LIMIT:
            return json.dumps(
                {
                    "success": False,
                    "error": f"记忆容量不足: 当前 {current_chars}/{MEMORY_CHAR_LIMIT} 字符，"
                             f"新增 {new_entry_chars} 字符会超出限制。请先 replace 或 remove 现有条目。",
                    "current_usage": f"{current_chars}/{MEMORY_CHAR_LIMIT}",
                    "current_entries": sections.get(target, []),
                },
                ensure_ascii=False,
            )

        # 添加条目
        sections[target].append(content.strip())

        # 写入文件
        new_content = build_memory_content(sections)
        if write_memory(new_content):
            actual_chars, usage_percent = get_memory_usage(new_content)
            return json.dumps(
                {
                    "success": True,
                    "message": f"已添加到 [{target}]",
                    "usage": f"{actual_chars}/{MEMORY_CHAR_LIMIT} ({usage_percent:.0f}%)",
                },
                ensure_ascii=False,
            )
        return json.dumps({"success": False, "error": "写入 Memory.md 失败"}, ensure_ascii=False)

    def _replace(self, sections: dict[str, list[str]], target: str, old_text: str, content: str) -> str:
        """替换条目（子字符串匹配）"""
        if not old_text:
            return json.dumps(
                {"success": False, "error": "替换操作需要 old_text 参数（子字符串匹配）"},
                ensure_ascii=False,
            )
        if not content:
            return json.dumps(
                {"success": False, "error": "替换操作需要 content 参数"},
                ensure_ascii=False,
            )

        entries = sections.get(target, [])
        matches = find_matching_entries(entries, old_text)

        # 匹配结果处理
        if len(matches) == 0:
            return json.dumps(
                {
                    "success": False,
                    "error": f"未找到匹配的条目: '{old_text}'",
                    "current_entries": entries,
                },
                ensure_ascii=False,
            )
        elif len(matches) > 1:
            return json.dumps(
                {
                    "success": False,
                    "error": f"子字符串 '{old_text}' 匹配到多个条目，请提供更具体的子字符串",
                    "matches": [m[1] for m in matches],
                },
                ensure_ascii=False,
            )

        # 唯一匹配，执行替换
        idx = matches[0][0]
        sections[target][idx] = content.strip()

        # 写入文件
        new_content = build_memory_content(sections)
        if write_memory(new_content):
            actual_chars, usage_percent = get_memory_usage(new_content)
            return json.dumps(
                {
                    "success": True,
                    "message": f"已替换 [{target}] 中的条目",
                    "old": matches[0][1],
                    "new": content.strip(),
                    "usage": f"{actual_chars}/{MEMORY_CHAR_LIMIT} ({usage_percent:.0f}%)",
                },
                ensure_ascii=False,
            )
        return json.dumps({"success": False, "error": "写入 Memory.md 失败"}, ensure_ascii=False)

    def _remove(self, sections: dict[str, list[str]], target: str, old_text: str) -> str:
        """删除条目（子字符串匹配）"""
        if not old_text:
            return json.dumps(
                {"success": False, "error": "删除操作需要 old_text 参数（子字符串匹配）"},
                ensure_ascii=False,
            )

        entries = sections.get(target, [])
        matches = find_matching_entries(entries, old_text)

        # 匹配结果处理
        if len(matches) == 0:
            return json.dumps(
                {
                    "success": False,
                    "error": f"未找到匹配的条目: '{old_text}'",
                    "current_entries": entries,
                },
                ensure_ascii=False,
            )
        elif len(matches) > 1:
            return json.dumps(
                {
                    "success": False,
                    "error": f"子字符串 '{old_text}' 匹配到多个条目，请提供更具体的子字符串",
                    "matches": [m[1] for m in matches],
                },
                ensure_ascii=False,
            )

        # 唯一匹配，执行删除
        removed_entry = matches[0][1]
        sections[target].pop(matches[0][0])

        # 写入文件
        new_content = build_memory_content(sections)
        if write_memory(new_content):
            actual_chars, usage_percent = get_memory_usage(new_content)
            return json.dumps(
                {
                    "success": True,
                    "message": f"已从 [{target}] 删除条目",
                    "removed": removed_entry,
                    "usage": f"{actual_chars}/{MEMORY_CHAR_LIMIT} ({usage_percent:.0f}%)",
                },
                ensure_ascii=False,
            )
        return json.dumps({"success": False, "error": "写入 Memory.md 失败"}, ensure_ascii=False)


# 注册工具
registry.register(MemoryTool)
