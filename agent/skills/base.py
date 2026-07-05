"""Skill 基类与注册表

Skill 是可复用的指令集，每个 Skill 是一个文件夹：
  - SKILL.md（必须）：## description（轻量索引）+ 详细说明
  - *.py（可选）：该 skill 需要的脚本

启动时 SkillRegistry 自动扫描 agent/skills/*/SKILL.md 并注册。
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

# Skill 根目录
SKILLS_DIR = Path(__file__).parent


class SkillBase(ABC):
    """Skill 基类

    每个 Skill 对应 agent/skills/ 下的一个文件夹。
    子类可覆写 execute() 以实现脚本逻辑。
    """

    def __init__(self, folder: Path):
        self._folder = folder
        self._skilL_md = folder / "SKILL.md"
        self._cached_description: str | None = None
        self._cached_full_prompt: str | None = None

    @property
    def name(self) -> str:
        """skill 名称（文件夹名）"""
        return self._folder.name

    @property
    def path(self) -> Path:
        """skill 文件夹路径"""
        return self._folder

    def get_description(self) -> str:
        """从 SKILL.md 提取 ## description 到下一个 ## 之间的内容

        Returns:
            description 文本，提取失败时返回空字符串
        """
        if self._cached_description is not None:
            return self._cached_description

        try:
            content = self._skilL_md.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("SKILL.md 不存在: %s", self._skilL_md)
            self._cached_description = ""
            return ""

        # 正则：## description 到下一个 ## 或文件末尾
        match = re.search(
            r"##\s*description\s*\n(.+?)(?=\n##|\Z)",
            content,
            re.DOTALL,
        )
        if match:
            self._cached_description = match.group(1).strip()
        else:
            logger.warning("SKILL.md 缺少 ## description 段: %s", self._skilL_md)
            self._cached_description = ""

        return self._cached_description

    def get_full_prompt(self) -> str:
        """返回 SKILL.md 全文

        Returns:
            SKILL.md 内容，文件不存在时返回空字符串
        """
        if self._cached_full_prompt is not None:
            return self._cached_full_prompt

        try:
            self._cached_full_prompt = self._skilL_md.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("SKILL.md 不存在: %s", self._skilL_md)
            self._cached_full_prompt = ""

        return self._cached_full_prompt

    async def execute(self, **kwargs) -> str:
        """执行 skill 的脚本逻辑（可选覆写）

        默认实现返回空 JSON，表示该 skill 无脚本。
        """
        return json.dumps({"success": True, "message": "该 skill 无脚本"}, ensure_ascii=False)


class SkillRegistry:
    """Skill 注册表

    启动时自动扫描 agent/skills/*/SKILL.md，为每个文件夹创建 SkillBase 实例。
    子类文件夹可通过继承 SkillBase 覆写 execute()。
    """

    def __init__(self):
        self._skills: dict[str, SkillBase] = {}

    def scan_and_register(self, skills_dir: Path | None = None) -> None:
        """扫描 skill 目录并注册

        Args:
            skills_dir: skill 根目录，默认 agent/skills/
        """
        base = skills_dir or SKILLS_DIR
        if not base.is_dir():
            logger.warning("Skill 目录不存在: %s", base)
            return

        for folder in sorted(base.iterdir()):
            if not folder.is_dir():
                continue
            skill_md = folder / "SKILL.md"
            if not skill_md.is_file():
                logger.debug("跳过无 SKILL.md 的文件夹: %s", folder.name)
                continue
            self._register(folder)

    def _register(self, folder: Path) -> None:
        """注册单个 skill 文件夹"""
        skill = SkillBase(folder)
        self._skills[skill.name] = skill
        logger.info("已注册 skill: %s", skill.name)

    def get(self, name: str) -> SkillBase | None:
        """按名称获取 skill"""
        return self._skills.get(name)

    def get_all_names(self) -> list[str]:
        """获取所有已注册 skill 名称"""
        return list(self._skills.keys())

    def get_all_descriptions(self) -> str:
        """拼接所有 skill 的描述，用于注入 system prompt

        Returns:
            格式化的 skill 索引文本，无 skill 时返回空字符串
        """
        if not self._skills:
            return ""

        lines = ["## 可用 Skill", ""]
        for name, skill in self._skills.items():
            desc = skill.get_description()
            if desc:
                lines.append(f"### {name}")
                lines.append(desc)
                lines.append("")

        return "\n".join(lines)


# 全局注册表实例
skill_registry = SkillRegistry()
