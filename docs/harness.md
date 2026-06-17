# Agent Harness 架构

统一的 Agent 执行引擎，通过配置驱动不同场景。

## 1. Prompt（提示词系统）

### 设计原则

- **分层组装**：将 system prompt 分为 5 层，由 `build_system_prompt()` 动态组装
- **场景驱动**：根据 work 类型选择不同的角色、规则、动态内容
- **用户定制**：支持 USER.md 用户自定义配置
- **模板化**：支持变量注入（用户信息、JD 数据等）

### System Prompt 构建流程

```python
def build_system_prompt(work: str, dynamic_context: dict = None) -> str:
    """
    构建流程：
    1. 静态内容：核心身份、绝对红线
    2. 根据 work 选择角色定义 + 核心规则
    3. 获取所有工具的描述
    4. 读取 USER.md 用户自定义内容
    5. 根据 work 注入动态提示词
    """
    parts = [ 1.核心身份、绝对红线 ]

    # 2. 角色定义 + 核心规则（由 work 决定）
    parts.append(get_role_and_rules(work))

    # 3. 工具定义
    parts.append(_get_tools_description())

    # 4. USER.md 用户自定义内容
    parts.append(_get_user_md())

    # 5. 动态提示词（由 work 决定）
    if dynamic_context:
        parts.append(build_dynamic_prompt(work, dynamic_context))

    return "\n\n---\n\n".join(parts)
```

### 各场景角色定义

| work | 角色 | 核心规则 |
|------|------|----------|
| resume | 简历助手 | 逐步引导、合理编造、单页限制、STAR 格式 |
| interview | 面试官 | 专业严谨、循序渐进、即时反馈、场景还原 |
| job_find | 求职顾问 | 数据驱动、客观评估、策略建议 |
| analysis | 数据分析师 | 数据准确、可视化呈现、洞察导向 |

### 动态提示词

根据 work 类型注入不同的动态内容：

**interview 场景**：
- 面试轮次：第 X 轮 / 共 Y 轮
- 面试风格：技术面试 / 行为面试 / 压力面试
- 语气特征：专业严谨 / 友好轻松 / 严肃认真
- 当前考察维度：技术基础 / 项目深挖 / 场景设计

**job_find 场景**：
- 当前页面：岗位列表 / 岗位详情 / 匹配分析
- 搜索关键词
- 筛选条件

**resume 场景**：
- 简历状态：已有简历 / 待完善
- JD 状态：已解析 / 待解析

### USER.md

用户自定义配置文件，位于 `agent/USER.md`：

#### 记录什么
- 安全红线
- 输出风格、语言


## 2. State（状态设计）

### 设计原则

- **状态与配置分离**：State 只记录当前状态，配置从 `AGENT_CONFIGS` 读取
- **通用化**：不硬编码特定场景字段（如 `resume_data`），用通用 `tool_results` 替代
- **可序列化**：支持持久化到数据库，支持断线重连

### 状态字段

```python
@dataclass
class AgentState:
    # === 核心状态 ===
    messages: list[dict]          # LLM 对话历史（含 tool_calls）
    turn_count: int = 0           # 当前工具调用轮次

    # === 场景与身份 ===
    scenario: str = ""            # 场景标识：resume / interview / job_find / analysis
    user_id: int | None = None    # 用户 ID
    session_id: str = ""          # 会话 ID（UUID）

    # === 工具结果缓存 ===
    tool_results: dict[str, Any] = field(default_factory=dict)
    # key: 工具名，value: 工具返回结果
    # 替代硬编码的 resume_data，支持任意工具结果缓存

    # === 对话阶段 ===
    stage: str = ""               # 当前阶段（由各场景定义）

    # === 错误与统计 ===
    error: str | None = None      # 结构化错误信息
    usage: dict = field(default_factory=dict)  # token 使用统计
```

### 轮次控制

`max_turn_count` 不在 State 中，从 `AGENT_CONFIGS` 动态获取：

```python
# 不同场景不同轮次限制
AGENT_CONFIGS = {
    "resume":    {"max_rounds": 10},
    "interview": {"max_rounds": 5},
    "job_find":  {"max_rounds": 8},
    "analysis":  {"max_rounds": 5},
}

# 使用
config = AGENT_CONFIGS[state.scenario]
if state.turn_count >= config["max_rounds"]:
    # 强制结束
```

### 持久化

State 通过 `agent_sessions` 表持久化到数据库：

```sql
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,           -- session_id (UUID)
    user_id INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    stage TEXT,
    messages JSON NOT NULL,
    tool_results JSON,
    turn_count INTEGER DEFAULT 0,
    usage JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 序列化接口

```python
@dataclass
class AgentState:
    # ... 字段定义 ...

    def snapshot(self) -> dict:
        """导出可序列化的状态快照"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "scenario": self.scenario,
            "stage": self.stage,
            "messages": self.messages,
            "tool_results": self.tool_results,
            "turn_count": self.turn_count,
            "usage": self.usage,
        }

    @classmethod
    def restore(cls, data: dict) -> "AgentState":
        """从快照恢复状态"""
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            scenario=data["scenario"],
            stage=data.get("stage", ""),
            messages=data["messages"],
            tool_results=data.get("tool_results", {}),
            turn_count=data.get("turn_count", 0),
            usage=data.get("usage", {}),
        )
```

### 会话生命周期

```
用户请求（带 session_id 或为空）
    ↓
session_id 为空？ → 创建新会话（生成 UUID）
    ↓
从 DB 加载 state（AgentState.restore）
    ↓
追加用户消息 → 执行 Agent 循环
    ↓
保存到 DB（state.snapshot）
    ↓
返回响应 + session_id
```


## 3. Tools（工具系统）

### 设计原则

- **最大输出限制**：所有工具都有 `max_results_chars` 限制
- **注册表模式**：工具通过装饰器自动注册，无需手动维护列表
- **基类约束**：所有工具继承 `BaseTool`，保证接口一致
- **场景筛选**：每个工具声明适用场景，按场景过滤可用工具

### 组件

```
tools/
├── base.py        # BaseTool 抽象基类
├── registry.py    # ToolRegistry 注册表
├── jd_parser.py   # JD 解析工具
└── resume.py      # 简历读写工具
```

### 工具定义

```python
class BaseTool(ABC):
    name: str           # 工具名（function calling 用）
    description: str    # 工具描述（给 LLM 看）
    parameters: dict    # JSON Schema 参数定义
    max_results_chars: int  # 结果最大字符数限制
    scenarios: list[str]    # 适用场景列表，空列表表示通用

    async def execute(**kwargs) -> Any  # 执行逻辑
    def to_schema() -> dict             # 转 OpenAI schema
```

### 场景筛选

每个工具通过 `scenarios` 属性声明适用场景：

```python
class JDParserTool(BaseTool):
    @property
    def scenarios(self) -> list[str]:
        return ["resume", "job_find"]  # 仅简历和求职场景可用
```

注册表提供按场景过滤的方法：

```python
class ToolRegistry:
    def get_schemas_by_scenario(self, scenario: str) -> list[dict]:
        """获取指定场景的工具 schema（scenarios 为空或包含 scenario）"""
        ...

    def get_tools_by_scenario(self, scenario: str) -> dict[str, BaseTool]:
        """获取指定场景的工具实例"""
        ...
```

### 注册方式

```python
# tools/jd_parser.py
from agent.tools.registry import registry

class JDParserTool(BaseTool):
    ...

registry.register(JDParserTool)  # 自动注册
```

### 工具与 Service 的关系

```
Tool (agent/tools/)          Service (backend/services/)
    │                              │
    │  调用                         │  纯业务逻辑
    ├─────────────────────────────→│
    │                              │
  封装 I/O、格式转换            数据库操作、算法
```

- Tool 负责：参数解析、调用 Service、结果格式化
- Service 负责：纯业务逻辑，不关心 Agent 调用

---

## 4. Context（上下文管理）

### 设计原则

- **分层管理**：系统级、会话级、轮次级上下文
- **自动组装**：Harness 自动拼接，无需手动传递
- **从 State 读取**：上下文数据从 AgentState 获取，不硬编码

### 上下文层级

```
┌─────────────────────────────────────┐
│ System Context (固定)               │
│  - system_prompt (动态构建)         │
│  - tools_schema                     │
├─────────────────────────────────────┤
│ Session Context (从 State 读取)      │
│  - user_id                          │
│  - scenario                         │
│  - tool_results (工具结果缓存)       │
├─────────────────────────────────────┤
│ Conversation Context (每轮更新)      │
│  - messages (对话历史)              │
│  - current_message                  │
│  - stage (当前阶段)                 │
└─────────────────────────────────────┘
```

### 消息构建流程

```python
def _build_messages(state: AgentState, message: str) -> list[dict]:
    messages = []

    # 1. System prompt (根据 scenario 动态构建)
    dynamic_context = {
        "tool_results": state.tool_results,  # 从 State 获取工具结果
        "stage": state.stage,
        # interview 动态上下文从 tool_results 或 stage 推导
    }
    system_prompt = build_system_prompt(state.scenario, dynamic_context)
    messages.append({"role": "system", "content": system_prompt})

    # 2. 历史对话
    messages.extend(state.messages)

    # 3. 用户消息
    messages.append({"role": "user", "content": message})

    return messages
```

### 上下文压缩

#### 核心问题

LLM API 有固定的上下文窗口限制（DeepSeek v4-flash = 128k tokens）。对话轮次增加后历史消息累积会超出限制。需要在接近上限时自动压缩上下文，同时最大限度保留信息。

#### Token 计数

**方案：tiktoken 精确计数 + API usage 回读**

- DeepSeek 使用与 GPT 系列兼容的 tokenizer（cl100k_base），tiktoken 无额外 API 调用
- 每次 LLM 调用后，从响应 `usage` 字段回读实际消耗（最准确的累积方式）
- 压缩前用 tiktoken 预估消息 token 数，决定是否触发

```python
import tiktoken

def count_tokens(messages: list[dict], model: str = "cl100k_base") -> int:
    """估算消息列表的 token 数"""
    enc = tiktoken.get_encoding(model)
    total = 0
    for msg in messages:
        total += 4  # 每条消息固定开销（role、分隔符）
        if isinstance(msg.get("content"), str):
            total += len(enc.encode(msg["content"]))
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                total += len(enc.encode(json.dumps(tc, ensure_ascii=False)))
        if msg.get("role") == "tool":
            total += len(enc.encode(msg.get("content", "")))
    return total
```

#### 阈值配置

```python
CONTEXT_LIMITS = {
    "deepseek-v4-flash": 128_000,
    "deepseek-v4-pro": 200_000,
}

COMPRESS_THRESHOLD = 0.75  # 75% 触发压缩（128k 窗口 = 96k tokens）
```

#### 压缩流程

```
每次 LLM 调用完成后
    │
    ├─ 从 API 响应读取 usage，累加到 state.usage
    │
    ├─ 估算下一轮 token 数 = current_usage + 新 user message
    │
    └─ 是否 >= 75% 阈值？
         │
        否 → 继续正常流程
        是 → 触发压缩
              │
              ▼
    ┌─────────────────────────────────┐
    │  Step 1: 组装压缩请求            │      
    │  - 压缩提示词                    │
    │  - 全部历史 messages             │
    └──────────────┬──────────────────┘
                   │
                   ▼
    ┌─────────────────────────────────┐
    │  Step 2: 调用 LLM 执行压缩       │
    │  - 独立压缩请求（非主 Agent 循环）│
    │  - 输出：结构化摘要文本           │
    └──────────────┬──────────────────┘
                   │
               成功? ┤
              │      │
             是     否
              │      │
              ▼      ▼
    ┌──────────────┐  ┌──────────────────────┐
    │ Step 3a:     │  │ Step 3b: 失败处理     │
    │ 组合新上下文  │  │                      │
    │ = system +   │  │ 压缩所需空间          │
    │   摘要 +     │  │ + 当前 usage          │
    │   最近 3 轮  │  │ > 上下文上限？         │
    │              │  │   │          │        │
    │ 重置 usage   │  │  否          是       │
    │              │  │   │          │        │
    │ 继续正常流程  │  │  重试压缩   丢弃最早  │
    └──────────────┘  │            10% 消息   │
                      │            熔断器 +1  │
                      │            熔断器>3?  │
                      │           │        │  │
                      │          否        是 │
                      │           │        │  │
                      │       重试压缩    抛出 │
                      │               错误中断 │
                      └──────────────────────┘
```

#### 压缩策略

**新上下文组合：**

```
[system prompt]                    ← 原样保留（角色定义、工具描述必须完整）
[“此会话因为上一个会话的上下文耗尽而继续”+压缩摘要：前面 N 轮的摘要]         ← LLM 输出
[最近 3 轮的原始消息]               ← 保留短期上下文连贯
[当前 user message]                ← 新输入
```

#### 熔断器机制

```python
class CompressCircuitBreaker:
    """压缩熔断器

    - 每次压缩失败计数 +1
    - 计数 > 3 时中断压缩，抛出异常
    - 压缩成功后重置计数
    """
    max_retries: int = 3
    count: int = 0

    def record_failure(self):
        self.count += 1
        if self.count > self.max_retries:
            raise ContextCompressionError(
                "上下文压缩失败次数超限，请缩短对话或重新开始会话"
            )

    def record_success(self):
        self.count = 0
```

**失败处理逻辑：**

1. 压缩失败 → 检查：压缩所需空间 + 当前 usage 是否超过上限
2. 超过上限 → 丢弃最早 10% 的消息 → 熔断器 +1 → 重试
3. 熔断器 > 3 → 中断，返回错误给前端

#### 与 Agent 循环的集成

修改 `agent/core/loop.py` 的 `_build_messages()`：

```python
async def _build_messages(state: AgentState, user_message: str, config: Config) -> list[dict]:
    """构建发送给 LLM 的消息列表，含自动压缩"""
    system_prompt = build_system_prompt(state.scenario, ...)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(state.messages)
    messages.append({"role": "user", "content": user_message})

    # 检查是否需要压缩
    estimated_tokens = count_tokens(messages)
    limit = CONTEXT_LIMITS.get(config.model, 128_000)

    if estimated_tokens >= limit * COMPRESS_THRESHOLD:
        messages = await compress_context(state, system_prompt, config, limit)

    return messages
```

#### 前端交互

- 压缩对用户**完全透明**（自动执行，无感知）
- 压缩失败时，前端显示错误提示："对话内容过长，请重新开始会话"
- 不展示 usage 信息（目标用户非开发者）

---

## 5. Memory（记忆系统）

### 设计原则

- **短期记忆**：当前会话的对话历史，通过 `messages` 字段存储
- **工具记忆**：工具执行结果缓存，通过 `tool_results` 字段存储
- **持久化**：通过 `agent_sessions` 表存储到数据库，支持跨天恢复

### 记忆类型

```
Memory
├── Short-term (短期，当前会话)
│   ├── messages              # 完整对话历史
│   ├── turn_count            # 当前轮次
│   └── stage                 # 当前阶段
│
├── Working (工作记忆，工具结果缓存)
│   └── tool_results          # 通用工具结果缓存
│       ├── "parse_jd"        # JD 解析结果
│       ├── "parse_resume"    # 简历解析结果
│       └── ...               # 其他工具结果
│
└── Persistent (持久化，数据库)
    └── agent_sessions 表     # 会话状态快照
```

### 持久化流程

```
用户请求
    ↓
有 session_id？
    ├── 是 → 从 DB 加载 AgentState.restore()
    └── 否 → 创建新 AgentState（生成 session_id）
    ↓
执行 Agent 循环
    ↓
保存到 DB：AgentState.snapshot() → agent_sessions 表
    ↓
返回响应 + session_id
```

---

## 6. Agent 配置

统一配置驱动不同场景：

```python
AGENT_CONFIGS = {
    "resume": {
        "work": "resume",
        "model": "deepseek-v4-flash",
        "temperature": 0.4,
        "max_rounds": 10,
        "context_config": {
            "include_resume": True,
            "include_jd": True,
            "max_history_rounds": 20,
        },
    },
    "interview": {
        "work": "interview",
        "model": "deepseek-v4-flash",
        "temperature": 0.7,
        "max_rounds": 5,
        "context_config": {
            "include_resume": True,
            "include_jd": False,
            "max_history_rounds": 10,
        },
    },
    "job_find": {
        "work": "job_find",
        "model": "deepseek-v4-flash",
        "temperature": 0.5,
        "max_rounds": 8,
        "context_config": {
            "include_resume": True,
            "include_jd": True,
            "max_history_rounds": 15,
        },
    },
    "analysis": {
        "work": "analysis",
        "model": "deepseek-v4-flash",
        "temperature": 0.3,
        "max_rounds": 5,
        "context_config": {
            "include_resume": True,
            "include_jd": True,
            "max_history_rounds": 10,
        },
    },
}
```

---

## 7. 执行流程

```
用户请求（带 session_id 或为空）
    ↓
路由层 (routers/)
    ↓
选择 Agent 配置 (agent_name)
    ↓
加载或创建 State
    ├── 有 session_id → 从 DB 加载 AgentState.restore()
    └── 无 session_id → 创建新 AgentState（生成 UUID）
    ↓
Harness 初始化
    ├── 加载 Prompt (build_system_prompt)
    ├── 加载 Tools (get_all_tools)
    └── 构建 messages (从 State 读取历史)
    ↓
Agent Loop
    ├── 构建 messages (含动态 system prompt)
    ├── 调用 LLM
    ├── 有 tool_calls?
    │   ├── 是 → 执行 Tools → 结果加入 messages → 继续循环
    │   └── 否 → 返回响应
    └── 超过 max_rounds? → 强制结束
    ↓
保存 State 到 DB（state.snapshot）
    ↓
返回结果 + session_id
```

---

## 8. 扩展新 Agent

只需 3 步：

1. **添加角色定义**：在 `prompts/roles.py` 的 `ROLES` 字典中添加新场景
2. **添加动态模板**（可选）：在 `prompts/dynamic.py` 的 `DYNAMIC_TEMPLATES` 中添加
3. **添加路由**（如需要）：`routers/new_agent.py`

无需修改 Harness 核心代码。

### 添加新工具

1. 在 `tools/` 下创建新工具类，继承 `BaseTool`
2. 实现必要的属性和方法
3. 调用 `registry.register()` 注册

---

## 9. API 调用示例

### 获取工具

```python
from agent.tools.registry import registry

# 获取所有工具
all_tools = registry.get_all_tools()
all_schemas = registry.get_all_schemas()
```

### 构建 system prompt

```python
from agent.prompts.build_prompt import build_system_prompt

# 简历助手场景
resume_prompt = build_system_prompt("resume", {
    "tool_results": {"parse_jd": jd_data, "parse_resume": resume_data},
    "stage": "编辑",
})

# 面试场景
interview_prompt = build_system_prompt("interview", {
    "tool_results": {"parse_resume": resume_data},
    "stage": "技术题",
})
```

### 会话持久化

```python
from agent.core.state import AgentState

# 从 DB 加载
state = AgentState.restore(db_data)

# 保存到 DB
snapshot = state.snapshot()
# 写入 agent_sessions 表
```
