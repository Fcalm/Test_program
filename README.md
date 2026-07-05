# AGENT 实习助手

基于 Harness 架构的 AI 求职助手，支持简历优化、面试模拟、求职分析等场景，通过多轮工具调用和流式输出为用户提供智能化求职服务。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 |
| 数据库 | SQLite (aiosqlite)，零配置单文件 |
| LLM | DeepSeek API，通过 OpenAI SDK 调用 |
| 前端 | React 19 + CSS Modules + Vite |
| 认证 | JWT + bcrypt |

## 项目结构

```
backend/
  main.py                  # FastAPI 入口
  config.py                # 配置（Pydantic Settings，从 .env 读取）
  database.py              # SQLite 异步引擎 + 会话管理
  provider_config.py       # LLM Provider 配置（config.yaml 解析）
  models/                  # SQLAlchemy 2.0 Mapped 模型
  schemas/                 # Pydantic v2 请求/响应模型
  services/                # 业务逻辑（DB session 由 router 传入）
  routers/                 # 薄路由层（校验 → 调 service → 返回）
  utils/                   # auth (JWT + bcrypt)、crypto

agent/
  core/                    # Agent 循环核心
    baseagent.py           # BaseAgent 基类（run / run_stream）
    client.py              # LLM 客户端工厂（OpenAI SDK）
    state.py               # AgentState 数据结构
    loop.py                # 循环辅助
  hooks/                   # 生命周期 Hook
    compact_hook.py        # 上下文压缩（双层：滚动摘要 + 全量压缩）
    compress_guard.py      # CompressGuard 守卫（防递归/状态污染）
  prompts/                 # 提示词系统
    build_prompt.py        # System Prompt 分层组装
    roles.py               # 场景角色定义
    dynamic.py             # 动态提示词注入
    compact.py             # 压缩提示词模板
  tools/                   # 工具系统
    basetool.py            # BaseTool 基类
    registry.py            # 工具注册表（含熔断器）
    jd_parser.py           # JD 解析工具
    read_file.py           # 文件读取工具
    database.py            # 简历数据库操作工具
    memory.py              # 记忆提取工具
  services/
    agent.py               # Agent 会话服务
    match_score.py         # JD-简历匹配评分（纯算法，不调 LLM）

frontend/src/
  pages/                   # 页面组件
    Resume.jsx             # 简历编辑页
    InterviewChat.jsx      # 面试模拟页
    InterviewList.jsx      # 面试列表页
    InterviewReport.jsx    # 面试报告页
    JobFinder.jsx          # 求职分析页
    Dashboard.jsx          # 仪表盘
    Login.jsx / Register.jsx / Survey.jsx
  components/              # 通用组件
    ChatInput.jsx          # 聊天输入框（支持文件上传）
    ChatMessage.jsx        # 消息气泡（Markdown 渲染）
    Sidebar.jsx / Layout.jsx / Modal.jsx / Toast.jsx ...
  hooks/                   # 自定义 Hooks
    useSSE.js              # SSE 流式请求 Hook
    useAuth.jsx            # 认证 Hook
  lib/
    api.js                 # API 请求封装（自动注入 Token）

config.yaml                # LLM Provider 配置（模型列表、上下文窗口）
docs/                      # 项目文档
```

## 快速开始

### 1. 环境准备

```bash
# Python 3.10+
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # Linux/Mac

pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
# JWT
SECRET_KEY=<随机密钥>
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# LLM
OPENAI_API_KEY=<你的 DeepSeek API Key>
OPENAI_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_HIGHER_MODEL=deepseek-v4-pro
```

### 3. 启动后端

```bash
uvicorn backend.main:app --reload
```

数据库 (`data/app.db`) 在首次启动时自动创建。

API 文档：http://localhost:8000/docs

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

## 核心设计

### Harness Agent 架构

Agent 采用手动 function-calling 循环（非 LangGraph），通过配置驱动不同场景：

```
build_system_prompt(work, dynamic_context)
  → 选择角色定义 + 核心规则 (roles.py)
  → 获取工具描述 (registry)
  → 读取用户自定义配置 (USER.md)
  → 注入动态提示词 (dynamic.py)
  → 组装完整 System Prompt
```

### 四大场景

| 场景 | work | 最大轮次 | 核心能力 |
|---|---|---|---|
| 简历助手 | `resume` | 10 轮 | 逐步引导优化简历、JD 匹配分析 |
| 面试模拟 | `interview` | 5 轮 | 多轮面试问答、即时反馈评分 |
| 求职分析 | `job_find` | 8 轮 | 岗位匹配评分、求职策略建议 |
| 数据分析 | `analysis` | 5 轮 | 简历数据统计与可视化洞察 |

### 上下文管理

- **System Prompt 分层组装**：静态角色规则 + 动态场景上下文 + 工具描述 + 用户配置，提高缓存命中率
- **四重记忆机制**：滚动摘要 → 压缩摘要 → 会话记忆 → 持久记忆(Memory.md)，逐层保留关键信息
- **双层压缩**：第一层按 Token 消耗 10% 更新滚动摘要，第二层在 75% 阈值触发全量 LLM 压缩
- **CompressGuard**：三态守卫（压缩中/工具执行中/流式输出中），防止递归压缩和状态污染

### 容错体系

- **熔断器**：工具连续失败 3 次自动移出可用列表 5 分钟，冷却后自动恢复
- **重试预算**：工具执行 3 次指数退避重试（1s/2s/4s），耗尽后馈入熔断器
- **轮次限制**：场景级最大轮次防无限循环，超时返回明确提示
- **降级策略**：Token 统计降级为字符估算，压缩失败逐次丢弃旧消息重试


