"""数据库工具 - 通用读写"""

import json
from agent.tools.basetool import BaseTool
from agent.tools.registry import registry


class ReadDBTool(BaseTool):
    """从数据库读取指定表的数据"""

    @property
    def name(self) -> str:
        return "read_db"

    @property
    def description(self) -> str:
        from backend.services.db_service import TABLE_SCHEMAS
        tables = ", ".join(TABLE_SCHEMAS.keys())
        return f"从数据库读取指定表的数据。支持的表：{tables}。"

    @property
    def parameters(self) -> dict:
        from backend.services.db_service import TABLE_SCHEMAS
        return {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "表名",
                    "enum": list(TABLE_SCHEMAS.keys())
                },
                "query": {
                    "type": "object",
                    "description": "查询条件（键值对）",
                    "additionalProperties": True
                }
            },
            "required": ["table_name", "query"]
        }

    @property
    def max_results_chars(self) -> int:
        return 8000

    @property
    def scenarios(self) -> list[str]:
        return []  # 通用

    async def execute(self, **kwargs) -> str:
        """读取指定表的数据"""
        from backend.services.db_service import read_table

        db = kwargs.get("db")
        if not db:
            return json.dumps({"success": False, "error": "缺少数据库连接"}, ensure_ascii=False)

        table_name = kwargs.get("table_name")
        query = kwargs.get("query", {})

        result = await read_table(db, table_name, query)
        return json.dumps(result, ensure_ascii=False, default=str)


class EditDBTool(BaseTool):
    """创建或更新指定表的数据"""

    @property
    def name(self) -> str:
        return "edit_db"

    @property
    def description(self) -> str:
        from backend.services.db_service import TABLE_SCHEMAS
        tables = ", ".join(TABLE_SCHEMAS.keys())
        return f"创建或更新指定表的数据。支持的表：{tables}。"

    @property
    def parameters(self) -> dict:
        from backend.services.db_service import TABLE_SCHEMAS
        return {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "表名",
                    "enum": list(TABLE_SCHEMAS.keys())
                },
                "query": {
                    "type": "object",
                    "description": "查询条件（用于定位记录）",
                    "additionalProperties": True
                },
                "data": {
                    "type": "object",
                    "description": "要更新的数据（键值对）",
                    "additionalProperties": True
                }
            },
            "required": ["table_name", "query", "data"]
        }

    @property
    def max_results_chars(self) -> int:
        return 2000

    @property
    def scenarios(self) -> list[str]:
        return []  # 通用

    async def execute(self, **kwargs) -> str:
        """创建或更新指定表的数据"""
        from backend.services.db_service import edit_table

        db = kwargs.get("db")
        if not db:
            return json.dumps({"success": False, "error": "缺少数据库连接"}, ensure_ascii=False)

        table_name = kwargs.get("table_name")
        query = kwargs.get("query", {})
        data = kwargs.get("data", {})

        result = await edit_table(db, table_name, query, data)
        return json.dumps(result, ensure_ascii=False)


# 注册工具
registry.register(ReadDBTool)
registry.register(EditDBTool)
