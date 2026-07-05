"""build_prompt 模块测试"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent.prompts.build_prompt import build_static_prompt, build_system_prompt, _get_tools_description, _get_memory_md, STABLE_PROMPT


class TestBuildStaticPrompt:
    """测试 build_static_prompt 函数"""

    def test_resume_work(self):
        """测试 resume 场景的静态 prompt 构建"""
        prompt = build_static_prompt("resume")

        # 应包含角色定义
        assert "简历编写助手" in prompt
        assert "中文" in prompt

        # 应包含工具描述
        assert "可用工具" in prompt
        assert "parse_jd_tool" in prompt

    def test_interview_work(self):
        """测试 interview 场景的静态 prompt 构建"""
        prompt = build_static_prompt("interview")

        # 应包含面试官角色
        assert "面试官" in prompt
        assert "面试" in prompt

    def test_job_find_work(self):
        """测试 job_find 场景的静态 prompt 构建"""
        prompt = build_static_prompt("job_find")

        # 应包含求职顾问角色
        assert "求职顾问" in prompt

    def test_analysis_work(self):
        """测试 analysis 场景的静态 prompt 构建"""
        prompt = build_static_prompt("analysis")

        # 应包含面试分析师角色
        assert "面试分析师" in prompt

    def test_unknown_work_defaults_to_resume(self):
        """测试未知 work 类型默认使用 resume 角色"""
        prompt = build_static_prompt("unknown_work")

        # 应默认使用简历编写助手角色
        assert "简历编写助手" in prompt

    def test_sections_separated_by_divider(self):
        """测试各部分用分隔符分隔"""
        prompt = build_static_prompt("resume")

        # 应包含分隔符
        assert "---" in prompt


class TestBuildSystemPrompt:
    """测试 build_system_prompt 函数（静态 + 动态组装）"""

    def test_static_only(self):
        """测试仅静态 prompt 的情况"""
        static_prompt = build_static_prompt("resume")
        prompt = build_system_prompt(static_prompt, None)

        # 应包含静态内容
        assert "简历编写助手" in prompt
        assert "可用工具" in prompt

    def test_dynamic_context_interview(self):
        """测试 interview 场景的动态上下文注入"""
        static_prompt = build_static_prompt("interview")
        context = {
            "work": "interview",
            "round": 2,
        }
        prompt = build_system_prompt(static_prompt, context)

        # 应包含动态信息
        assert "第 2 轮" in prompt

    def test_dynamic_context_resume_with_key_data(self):
        """测试 resume 场景有关键数据时的动态上下文"""
        static_prompt = build_static_prompt("resume")
        context = {
            "work": "resume",
            "key_data": {
                "parse_resume": {
                    "success": True,
                    "basic_info": {"name": "张三"},
                    "education": [{"school": "清华大学"}],
                    "internship_exp": [{"company": "字节跳动"}],
                    "project_exp": [{"name": "项目A"}],
                },
            },
        }
        prompt = build_system_prompt(static_prompt, context)

        # 应包含简历状态
        assert "已有简历数据" in prompt
        assert "张三" in prompt
        assert "清华大学" in prompt

    def test_dynamic_context_resume_without_resume(self):
        """测试 resume 场景无简历时的动态上下文"""
        static_prompt = build_static_prompt("resume")
        context = {
            "work": "resume",
            "key_data": {},
        }
        prompt = build_system_prompt(static_prompt, context)

        # 应显示无简历状态
        assert "尚未提供简历数据" in prompt

    def test_dynamic_context_with_jd(self):
        """测试有 JD 数据时的动态上下文"""
        static_prompt = build_static_prompt("resume")
        context = {
            "work": "resume",
            "key_data": {
                "parse_jd": {
                    "success": True,
                    "company": "字节跳动",
                    "position": "后端开发",
                    "key_skills": ["Python", "Go", "MySQL"],
                },
            },
        }
        prompt = build_system_prompt(static_prompt, context)

        # 应包含 JD 信息
        assert "字节跳动" in prompt
        assert "后端开发" in prompt
        assert "Python" in prompt


class TestGetToolsDescription:
    """测试 _get_tools_description 函数"""

    def test_returns_tool_descriptions(self):
        """测试返回工具描述"""
        desc = _get_tools_description()

        # 应包含所有注册的工具
        assert "parse_jd_tool" in desc
        assert "read_file" in desc

    def test_contains_description_header(self):
        """测试包含描述标题"""
        desc = _get_tools_description()

        assert "## 可用工具" in desc

    def test_each_tool_has_description(self):
        """测试每个工具都有描述"""
        desc = _get_tools_description()

        # 每个工具应有 ### 标题
        assert "### parse_jd_tool" in desc
        assert "### read_file" in desc


class TestGetMemoryMd:
    """测试 _get_memory_md 函数"""

    @patch("agent.prompts.build_prompt.MEMORY_MD_PATH")
    def test_file_exists_with_content(self, mock_path):
        """测试文件存在且有内容时读取"""
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = """## 用户偏好
- 喜欢简洁风格

## 工作习惯
- 反复打磨措辞

## 项目约定
- 简历单页

## 关键教训
- 成果要实际
"""

        result = _get_memory_md()

        # 应包含持久化记忆标头
        assert "MEMORY" in result
        assert "持久化记忆" in result
        # 应包含内容
        assert "用户偏好" in result
        assert "喜欢简洁风格" in result
        # 应使用 § 分隔
        assert "§" in result

    @patch("agent.prompts.build_prompt.MEMORY_MD_PATH")
    def test_file_not_exists(self, mock_path):
        """测试文件不存在时返回空字符串"""
        mock_path.exists.return_value = False

        result = _get_memory_md()

        assert result == ""

    @patch("agent.prompts.build_prompt.MEMORY_MD_PATH")
    def test_file_empty(self, mock_path):
        """测试文件为空时返回空字符串"""
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = ""

        result = _get_memory_md()

        assert result == ""

    @patch("agent.prompts.build_prompt.MEMORY_MD_PATH")
    def test_read_error(self, mock_path):
        """测试读取错误时返回空字符串"""
        mock_path.exists.return_value = True
        mock_path.read_text.side_effect = Exception("Read error")

        result = _get_memory_md()

        assert result == ""

    @patch("agent.prompts.build_prompt.MEMORY_MD_PATH")
    def test_contains_usage_percentage(self, mock_path):
        """测试包含使用率百分比"""
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = """## 用户偏好
- 喜欢简洁风格

## 工作习惯


## 项目约定


## 关键教训
"""

        result = _get_memory_md()

        # 应包含使用率信息
        assert "%" in result
        assert "chars" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
