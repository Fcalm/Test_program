"""数据库工具 - 简历读写"""

import json
from agent.tools.basetool import BaseTool
from agent.tools.registry import registry


class ReadDBTool(BaseTool):
    """从数据库读取用户简历"""

    @property
    def name(self) -> str:
        return "read_db"

    @property
    def description(self) -> str:
        return "从数据库读取当前用户的简历数据。返回简历的各个模块（基本信息、教育经历、实习经历、项目经历、个人优势）。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    @property
    def max_results_chars(self) -> int:
        return 8000

    @property
    def scenarios(self) -> list[str]:
        return ["resume", "interview", "job_find", "analysis"]

    async def execute(self, **kwargs) -> str:
        """读取简历"""
        from backend.database import async_session_maker
        from backend.services.resume import get_resume

        user_id = kwargs.get("user_id")
        if not user_id:
            return json.dumps({"success": False, "error": "缺少 user_id"}, ensure_ascii=False)

        async with async_session_maker() as db:
            resume = await get_resume(db, user_id)

            if not resume:
                return json.dumps({"success": True, "data": None, "message": "暂无简历数据"}, ensure_ascii=False)

            data = {
                "basic_info": resume.basic_info,
                "education": resume.education,
                "internship_exp": resume.internship_exp,
                "project_exp": resume.project_exp,
                "personal_strengths": resume.personal_strengths,
            }
            return json.dumps({"success": True, "data": data}, ensure_ascii=False)


class EditDBTool(BaseTool):
    """创建或更新用户简历"""

    @property
    def name(self) -> str:
        return "edit_db"

    @property
    def description(self) -> str:
        return "创建或更新用户简历。支持部分更新（只传需要修改的字段）。可更新字段：basic_info, education, internship_exp, project_exp, personal_strengths。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "basic_info": {
                    "type": "object",
                    "description": "基本信息（姓名、邮箱、电话等）",
                    "additionalProperties": True
                },
                "education": {
                    "type": "array",
                    "description": "教育经历列表",
                    "items": {"type": "object", "additionalProperties": True}
                },
                "internship_exp": {
                    "type": "array",
                    "description": "实习经历列表",
                    "items": {"type": "object", "additionalProperties": True}
                },
                "project_exp": {
                    "type": "array",
                    "description": "项目经历列表",
                    "items": {"type": "object", "additionalProperties": True}
                },
                "personal_strengths": {
                    "type": "array",
                    "description": "个人优势列表",
                    "items": {"type": "string"}
                }
            },
            "required": []
        }

    @property
    def max_results_chars(self) -> int:
        return 2000

    @property
    def scenarios(self) -> list[str]:
        return ["resume"]

    async def execute(self, **kwargs) -> str:
        """创建或更新简历"""
        from backend.database import async_session_maker
        from backend.services.resume import get_resume, create_resume, update_resume

        user_id = kwargs.get("user_id")
        if not user_id:
            return json.dumps({"success": False, "error": "缺少 user_id"}, ensure_ascii=False)

        # 提取要更新的字段（只取非 None 的）
        update_data = {
            k: v for k, v in kwargs.items()
            if k != "user_id" and v is not None
        }

        if not update_data:
            return json.dumps({"success": False, "error": "没有提供要更新的数据"}, ensure_ascii=False)

        async with async_session_maker() as db:
            resume = await get_resume(db, user_id)

            if resume:
                # 更新现有简历
                await update_resume(db, resume, update_data)
                return json.dumps({
                    "success": True,
                    "message": "简历已更新",
                    "updated_fields": list(update_data.keys())
                }, ensure_ascii=False)
            else:
                # 创建新简历
                await create_resume(db, user_id, update_data)
                return json.dumps({
                    "success": True,
                    "message": "简历已创建",
                    "created_fields": list(update_data.keys())
                }, ensure_ascii=False)


# 注册工具
registry.register(ReadDBTool)
registry.register(EditDBTool)
