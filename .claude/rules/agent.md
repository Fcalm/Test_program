# Agent / LLM 集成规则

## 技术方案

- 使用 OpenAI Python SDK（`openai.AsyncOpenAI`）调用 DeepSeek API
- **非 LangGraph** — 实现为手动 function-calling 循环（最多 10 轮）
- 支持流式（SSE）和非流式两种模式
- **Harness 架构**：统一的 Agent 执行引擎，通过配置驱动不同场景

## 配置

```python
# backend/config.py 中的 settings
OPENAI_API_KEY       # DeepSeek API key
OPENAI_BASE_URL      # https://api.deepseek.com
OPENAI_MODEL         # deepseek-v4-flash
```

- 所有配置从 `settings` 对象读取，**禁止硬编码**

## Harness 架构

### 核心组件

```
agent/
├── harness.md        # 架构文档
├── USER.md           # 用户自定义配置
├── core/             # Agent 循环核心
├── prompts/          # 提示词系统
│   ├── build_prompt.py  # 构建逻辑
│   ├── roles.py         # 角色定义
│   └── dynamic.py       # 动态提示词
├── tools/            # 工具系统
│   ├── base.py          # BaseTool 基类
│   ├── registry.py      # 工具注册表
│   └── *.py             # 具体工具
├── routers/          # 路由层
├── schemas/          # Schema 定义
└── services/         # 业务服务
```

### System Prompt 构建流程

`agent/prompts/build_prompt.py` 中的核心逻辑：

```
build_system_prompt(work, dynamic_context)
    ↓
1. 根据 work 选择角色定义 + 核心规则 (roles.py)
2. 获取所有工具的描述 (registry)
3. 读取 USER.md 用户自定义内容
4. 根据 work 注入动态提示词 (dynamic.py)
    ↓
组装完成的 system prompt
```

## 工具定义

当前 4 个工具（定义在 `agent/tools/` 目录）：

| 工具名 | 功能 | 调用的服务 |
|---|---|---|
| `parse_jd_tool` | 解析 JD 文本 | `jd_parser.parse_jd()` |
| `parse_resume_tool` | 解析简历纯文本 | `resume_parser` |
| `get_resume_table_tool` | 读取用户简历 | `resume.get_resume()` |
| `save_resume_table_tool` | 保存简历到 DB | `resume.create_resume()` |

新增工具时：
1. 在 `agent/tools/` 创建新工具类，继承 `BaseTool`
2. 实现必要的属性和方法
3. 调用 `registry.register()` 注册
4. 在对应场景的 prompt 中添加工具使用说明

## 角色定义

`agent/prompts/roles.py` 定义各场景的角色和规则：

| work | 角色 | 核心规则 |
|------|------|----------|
| resume | 简历助手 | 逐步引导、合理编造、单页限制、STAR 格式 |
| interview | 面试官 | 专业严谨、循序渐进、即时反馈、场景还原 |
| job_find | 求职顾问 | 数据驱动、客观评估、策略建议 |
| analysis | 数据分析师 | 数据准确、可视化呈现、洞察导向 |

## 动态提示词

`agent/prompts/dynamic.py` 定义各场景的动态内容：

- **interview**：面试轮次、面试风格、语气特征、当前考察维度
- **job_find**：当前页面、搜索关键词、筛选条件
- **resume**：简历状态、JD 状态
- **analysis**：分析类型、数据范围

## Agent 配置

```python
AGENT_CONFIGS = {
    "resume": {
        "work": "resume",
        "model": "deepseek-v4-flash",
        "temperature": 0.4,
        "max_rounds": 10,
    },
    "interview": {
        "work": "interview",
        "model": "deepseek-v4-flash",
        "temperature": 0.7,
        "max_rounds": 5,
    },
    "job_find": {
        "work": "job_find",
        "model": "deepseek-v4-flash",
        "temperature": 0.5,
        "max_rounds": 8,
    },
    "analysis": {
        "work": "analysis",
        "model": "deepseek-v4-flash",
        "temperature": 0.3,
        "max_rounds": 5,
    },
}
```

## 流式 SSE

```python
# routers/agent.py
@router.post("/stream")
async def stream_chat(req: ChatRequest, ...):
    return StreamingResponse(
        chat_with_agent_stream(user_id, req.message, req.history),
        media_type="text/event-stream",
    )
```

- SSE 数据格式：`data: {"content": "...", "type": "thinking"|"answer"|"tool_call"}\n\n`
- 流式模式下 reasoning_content 和 function_call 分别推送

## 匹配评分

`services/match_score.py` — 纯算法，不调用 LLM：

| 维度 | 分值 | 计算方式 |
|---|---|---|
| 技能匹配 | 40 分 | JD 要求 vs 简历技能关键词交集 |
| 经验匹配 | 30 分 | 工作年限 + 实习经历相关性 |
| 学历匹配 | 15 分 | 学历等级对比 |
| 关键词匹配 | 15 分 | JD 全文 vs 简历关键词覆盖 |

## 验证方式

- 工具定义的 `parameters` schema 与实际 service 函数签名不匹配 → 不完整
- Agent 循环缺少最大迭代限制 → 风险，必须有上限
- API key 直接写在代码中而非从 settings 读取 → 违规
- System prompt 未使用 `build_system_prompt()` 动态构建 → 违规
