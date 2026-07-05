"""通用数据库操作服务"""

import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# 支持的表及其字段定义（移除 agent_sessions 写入权限，移除已合并的 file_texts）
TABLE_SCHEMAS = {
    "resumes": {
        "key_field": "user_id",
        "fields": ["basic_info", "education", "internship_exp", "project_exp", "personal_strengths"],
    },
    "uploaded_files": {
        "key_field": "user_id",
        "fields": ["original_name", "storage_path", "file_type", "file_size", "raw_text", "char_count", "content_hash"],
    },
    "analysis_reports": {
        "key_field": "session_id",
        "fields": ["user_id", "report_data", "status"],
    },
}

# 只读表（LLM 可读不可写）
READONLY_TABLES = {"agent_sessions", "users"}

# 完整表 schema（包含只读表，用于读取）
ALL_TABLE_SCHEMAS = {
    **TABLE_SCHEMAS,
    "agent_sessions": {
        "key_field": "user_id",
        "fields": ["scenario", "messages", "key_data", "usage", "turn_count", "error"],
    },
    "users": {
        "key_field": "id",
        "fields": ["username", "email", "is_active"],
    },
}


async def read_table(
    db: AsyncSession,
    table_name: str,
    query: dict,
) -> dict:
    """
    读取指定表的数据。

    Returns:
        {"success": True, "data": [...]} 或 {"success": False, "error": "..."}
    """
    if table_name not in ALL_TABLE_SCHEMAS:
        return {"success": False, "error": f"不支持的表：{table_name}"}

    # 构建查询
    where_clauses = []
    params = {}
    for key, value in query.items():
        where_clauses.append(f"{key} = :{key}")
        params[key] = value

    where_str = " AND ".join(where_clauses) if where_clauses else "1=1"
    sql = f"SELECT * FROM {table_name} WHERE {where_str}"

    result = await db.execute(text(sql), params)
    rows = result.mappings().all()

    if not rows:
        return {"success": True, "data": [], "message": "未找到数据"}

    data = [dict(row) for row in rows]
    return {"success": True, "data": data}


async def edit_table(
    db: AsyncSession,
    table_name: str,
    query: dict,
    data: dict,
) -> dict:
    """
    创建或更新指定表的数据。

    Returns:
        {"success": True, "message": "..."} 或 {"success": False, "error": "..."}
    """
    if table_name not in TABLE_SCHEMAS:
        if table_name in READONLY_TABLES:
            return {"success": False, "error": f"表 {table_name} 为只读，不可修改"}
        return {"success": False, "error": f"不支持的表：{table_name}"}

    if not data:
        return {"success": False, "error": "没有提供要更新的数据"}

    # 先检查记录是否存在
    where_clauses = []
    params = {}
    for key, value in query.items():
        where_clauses.append(f"{key} = :{key}")
        params[key] = value

    where_str = " AND ".join(where_clauses) if where_clauses else "1=1"
    check_sql = f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {where_str}"
    result = await db.execute(text(check_sql), params)
    exists = result.scalar() > 0

    # 自动序列化 JSON 字段
    def _serialize_json_fields(d: dict) -> dict:
        """将 dict/list 类型的值序列化为 JSON 字符串"""
        result = {}
        for key, value in d.items():
            if isinstance(value, (dict, list)):
                result[key] = json.dumps(value, ensure_ascii=False)
            else:
                result[key] = value
        return result

    if exists:
        # 更新
        set_clauses = []
        update_params = dict(params)
        serialized_data = _serialize_json_fields(data)
        for key, value in serialized_data.items():
            set_clauses.append(f"{key} = :set_{key}")
            update_params[f"set_{key}"] = value

        set_str = ", ".join(set_clauses)
        update_sql = f"UPDATE {table_name} SET {set_str} WHERE {where_str}"
        await db.execute(text(update_sql), update_params)
        await db.flush()

        return {
            "success": True,
            "message": f"{table_name} 已更新",
            "updated_fields": list(data.keys()),
        }
    else:
        # 插入
        all_data = {**query, **data}
        serialized_data = _serialize_json_fields(all_data)
        columns = ", ".join(serialized_data.keys())
        placeholders = ", ".join(f":{k}" for k in serialized_data.keys())
        insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        await db.execute(text(insert_sql), serialized_data)
        await db.flush()

        return {
            "success": True,
            "message": f"{table_name} 已创建",
            "created_fields": list(all_data.keys()),
        }
