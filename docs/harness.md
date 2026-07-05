# Agent Harness 架构

统一的 Agent 执行引擎，通过配置驱动不同场景。

## 1. Prompt（提示词系统）

### 设计原则

- **分层组装**：将 system prompt 分为 2 层，静态层和动态层，由 `build_system_prompt()` 动态组装
- **场景驱动**：根据 work 类型选择不同的角色、规则、可用工具、动态内容
- **静态缓存**：静态层提示词会话中冻结，不随对话而变

### System Prompt 构建流程

```python
def build_system_prompt(work: str, dynamic_context: dict = None) -> str:
    """
    构建流程：
    1. 静态内容：核心身份、绝对红线
    2. 根据 work 选择角色定义 + 核心规则
    3. 获取所有工具的描述
    4. 读取 Memory.md 持久化记忆（冻结快照）
    5. 根据 work 注入动态提示词
    """
    parts = [ 1.核心身份、绝对红线 ]

    # 2. 角色定义 + 核心规则（由 work 决定）
    parts.append(get_role_and_rules(work))

    # 3. 工具定义
    parts.append(_get_tools_description())

    # 4. Memory.md 持久化记忆（冻结快照，会话开始时读取一次）
    parts.append(_get_memory_md())

    ---- 动静层分离 ----

    # 5. 动态提示词（每轮循环都可能更新）
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

根据 work 类型注入不同的动态内容，仅在 `dynamic_context` 包含对应 key 时注入：

**resume 场景**：

```markdown
## 简历与 JD 状态:
- 当前简历id：{resume_id}
- 当前JDid：{jd_id}
```

**interview 场景**：

```markdown
## 当前面试状态:
- 面试轮次：第 {round} 轮 / 共2轮
```


### Memory.md

持久化记忆文件，位于 `agent/Memory.md`，**冻结快照**模式注入 system prompt：

#### 特性

- **自进化**：由 Agent 通过 memory 工具自动维护，无需用户手动编辑
- **冻结注入**：会话开始时读取一次，会话中不刷新（保留 LLM 前缀缓存）
- **字符上限**：2,200 字符（约 800 tokens），保持聚焦
- **代替 USER.md**：用户自定义内容价值不高，改为系统自动提炼

#### 存储内容

```markdown
## 用户偏好
- 喜欢简洁风格，不喜欢过度包装

## 工作习惯
- 修改简历时会反复打磨措辞

## 项目约定
- 简历单页、STAR格式

## 关键教训
- 成果描述要符合实际
```

#### 注入格式

```
══════════════════════════════════════════════
MEMORY (持久化记忆) [67% — 1,474/2,200 chars]
══════════════════════════════════════════════
用户偏好：喜欢简洁风格，不喜欢过度包装
§
工作习惯：修改简历时会反复打磨措辞
§
项目约定：简历单页、STAR格式
```

#### 提炼机制

详见第 6 节 Memory。


## 2. State（状态设计）

### 设计原则

- **状态与配置分离**：State 只记录当前状态，配置从 `AGENT_CONFIGS` 读取
- **可序列化**：支持持久化到数据库，支持断线重连

### 状态字段

```python
@dataclass
class AgentState:
    # === 核心状态 ===
    messages: list[dict]          # 上下文
    turn_count: int = 0           # 当前工具调用轮次

    # === 场景与身份 ===
    scenario: str = ""            # 场景标识：resume / interview / job_find / analysis
    user_id: int | None = None    # 用户 ID
    session_id: str = ""          # 会话 ID（UUID）

    # === 关键数据缓存 ===
    key_data: dict[str, Any] = field(default_factory=dict)
    # key: 数据标识，value: 缓存的数据
    # 通过 set_key_data / get_key_data 读写，替代硬编码的 resume_data

    # === 滚动摘要（工作笔记） ===
    summary: str = ""             # 滚动摘要（每次更新覆盖）
    summary_token_checkpoint: int = 0  # 上次摘要更新时的累计 token 数

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

State 通过 `agent_sessions` 表持久化到 SQLite（`data/app.db`）：

```sql
-- 会话级状态（由 snapshot_session() 写入）
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,           -- session_id (UUID)
    user_id INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    title TEXT DEFAULT '',                    -- 会话标题
    messages TEXT NOT NULL DEFAULT '[]',      -- JSON 字符串
    key_data TEXT DEFAULT '{}',               -- JSON 字符串（原 tool_results）
    uploaded_file_ids TEXT DEFAULT '[]',      -- JSON 字符串
    summary TEXT DEFAULT '',                  -- 滚动摘要（工作笔记）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 循环级状态（由 snapshot_loop() 写入）
CREATE TABLE agent_loop_state (
    session_id TEXT PRIMARY KEY,   -- 关联 agent_sessions.id
    usage TEXT DEFAULT '{}',                   -- JSON 字符串（累计 token）
    summary_token_checkpoint INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
);
```

`turn_count`、`error`、`compact_count` 为纯内存态，不持久化 — `turn_count` / `compact_count` 每次请求重置，`error` 为单次请求错误。

**数据治理：** 每用户每场景最多保留 10 个会话，`save_session()` 时自动清理最旧的超出记录。

### 序列化接口

```python
@dataclass
class AgentState:
    # ... 字段定义 ...

    def set_key_data(self, key: str, value: Any) -> None:
        """写入关键数据缓存"""
        self.key_data[key] = value

    def get_key_data(self, key: str, default: Any = None) -> Any:
        """读取关键数据缓存"""
        return self.key_data.get(key, default)

    def snapshot_session(self) -> dict:
        """导出会话级状态（写入 agent_sessions 表）"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "scenario": self.scenario,
            "title": self.title,
            "messages": self.messages,
            "key_data": self.key_data,
            "uploaded_file_ids": self.uploaded_file_ids,
            "summary": self.summary,
        }

    def snapshot_loop(self) -> dict:
        """导出循环级状态（写入 agent_loop_state 表）"""
        return {
            "session_id": self.session_id,
            "usage": self.usage,
            "summary_token_checkpoint": self.summary_token_checkpoint,
        }

    @classmethod
    def restore(cls, session_data: dict, loop_data: dict | None = None) -> "AgentState":
        """从快照恢复状态（合并 session + loop 两张表）

        turn_count / error / compact_count 为纯内存态，不从 DB 恢复。
        """
        loop = loop_data or {}
        return cls(
            session_id=session_data["session_id"],
            user_id=session_data.get("user_id"),
            scenario=session_data.get("scenario", ""),
            title=session_data.get("title", ""),
            messages=session_data.get("messages", []),
            key_data=session_data.get("key_data", {}),
            uploaded_file_ids=session_data.get("uploaded_file_ids", []),
            summary=session_data.get("summary", ""),
            usage=loop.get("usage", {}),
            summary_token_checkpoint=loop.get("summary_token_checkpoint", 0),
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
保存到 DB（snapshot_session + snapshot_loop）
    ↓
返回响应 + session_id
```


## 3. Tools（工具系统）

### 设计原则

- **最大输出限制**：所有工具都有 `max_results_chars` 限制
- **注册表模式**：工具通过装饰器自动注册，无需手动维护列表
- **基类约束**：所有工具继承 `BaseTool`，保证接口一致
- **场景筛选**：每个工具声明适用场景，按场景过滤可用工具

### 工具定义

```python
class BaseTool(ABC):
    name: str           # 工具名（function calling 用）
    description: str    # 工具描述（给 LLM 看）
    parameters: dict    # JSON Schema 参数定义
    max_results_chars: int  # 结果最大字符数限制
    scenarios: list[str]    # 适用场景列表，空列表表示通用

    async def execute(**kwargs) -> ToolResult  # 执行逻辑（返回 ToolResult）
    def to_schema() -> dict                    # 转 OpenAI schema
```

### ToolResult Schema

所有工具统一返回 `ToolResult` 结构：

```python
@dataclass
class ToolResult:
    status: Literal["success", "error", "disabled"]  # 执行状态
    data: Any                                         # 工具返回的数据
    context: dict | None = None                       # 元信息（错误详情、重试次数等）

    def to_dict(self) -> dict:
        return {"status": self.status, "data": self.data, "context": self.context}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
```

**status 枚举：**

| status | 含义 | data | context |
|---|---|---|---|
| `success` | 正常执行 | 工具返回值 | `None` 或附加信息 |
| `error` | 执行失败（可重试） | `None` | `{"error": "错误描述", "retry_count": N}` |
| `disabled` | 工具已被熔断器禁用 | `None` | `{"reason": "...", "fail_count": 3, "available_at": "ISO时间"}` |

**示例：**

```python
# 成功
ToolResult(status="success", data={"skills": ["Python", "FastAPI"]})

# 失败
ToolResult(status="error", data=None, context={"error": "数据库连接超时", "retry_count": 1})

# 熔断禁用
ToolResult(status="disabled", data=None, context={
    "tool": "read_db",
    "reason": "连续失败 3 次，已临时禁用",
    "fail_count": 3,
    "available_at": "2026-06-18T15:30:00"
})
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

### 重试机制

工具执行失败时自动重试，采用**指数退避**策略，在 BaseAgent 层统一实现：

```python
# agent/core/baseagent.py 中的 _execute_tool 方法

async def _execute_tool(self, tool_name: str, kwargs: dict) -> ToolResult:
    """统一工具执行入口，含重试 + 熔断"""
    registry = self.registry

    # 1. 检查熔断器
    if registry.is_disabled(tool_name):
        return ToolResult(
            status="disabled",
            data=None,
            context=registry.get_disable_info(tool_name),
        )

    # 2. 重试循环
    max_retries = 3
    for attempt in range(max_retries):
        try:
            tool = registry.get(tool_name)
            result = await tool.execute(**kwargs)

            # 成功 → 重置失败计数
            if result.status == "success":
                registry.record_success(tool_name)
                return result

            # 工具主动返回 error → 记录失败
            registry.record_failure(tool_name)

        except Exception as e:
            registry.record_failure(tool_name)
            result = ToolResult(
                status="error",
                data=None,
                context={"error": str(e), "retry_count": attempt + 1},
            )

        # 未达上限 → 指数退避后重试
        if attempt < max_retries - 1:
            delay = 2 ** attempt  # 1s, 2s, 4s
            await asyncio.sleep(delay)

    # 3. 全部失败 → 触发熔断
    registry.trigger_circuit_breaker(tool_name)
    return ToolResult(
        status="disabled",
        data=None,
        context=registry.get_disable_info(tool_name),
    )
```

**重试时序：**

```
tool.execute() → 失败 (attempt 0)
    │
    ├─ wait 1s (2^0)
    │
    ├─ tool.execute() → 失败 (attempt 1)
    │
    ├─ wait 2s (2^1)
    │
    └─ tool.execute() → 失败 (attempt 2)
         │
         └─ 触发熔断器 → return ToolResult(status="disabled")
```

### 熔断器（Tool Circuit Breaker）

在 `ToolRegistry` 中实现，每个工具独立的熔断状态：

```python
class ToolRegistry:
    _tools: dict[str, BaseTool]
    _fail_counts: dict[str, int]           # 连续失败计数
    _disabled_tools: dict[str, datetime]   # 工具名 → 禁用到期时间

    MAX_RETRIES = 3
    DISABLE_DURATION = timedelta(minutes=5)  # 禁用 5 分钟后自动恢复
```

**核心方法：**

```python
def record_failure(self, tool_name: str):
    """记录一次失败"""
    self._fail_counts[tool_name] = self._fail_counts.get(tool_name, 0) + 1

def record_success(self, tool_name: str):
    """成功后重置计数"""
    self._fail_counts.pop(tool_name, None)
    self._disabled_tools.pop(tool_name, None)

def trigger_circuit_breaker(self, tool_name: str):
    """触发熔断：禁用工具"""
    self._disabled_tools[tool_name] = datetime.now() + self.DISABLE_DURATION
    self._fail_counts.pop(tool_name, None)

def is_disabled(self, tool_name: str) -> bool:
    """检查工具是否被禁用（含自动恢复）"""
    if tool_name not in self._disabled_tools:
        return False
    if datetime.now() >= self._disabled_tools[tool_name]:
        # TTL 到期 → 自动恢复
        self._disabled_tools.pop(tool_name)
        return False
    return True

def get_disable_info(self, tool_name: str) -> dict:
    """获取禁用信息（用于返回给 LLM）"""
    return {
        "tool": tool_name,
        "reason": f"连续失败 {self.MAX_RETRIES} 次，已临时禁用",
        "fail_count": self.MAX_RETRIES,
        "available_at": self._disabled_tools[tool_name].isoformat(),
    }
```

**熔断状态机：**

```
正常 ──失败──→ 计数中 (count 1,2,...)
  ↑              │
  │              ├──失败达到 3 次──→ 禁用 (5 分钟 TTL)
  │              │                      │
  │              └──成功────────→ 重置 ←─┘ TTL 到期自动恢复
  │
  └────────────────────────────────────────┘
```

**LLM 感知方式：**

工具被禁用时，tool result 直接返回 `status: "disabled"` 及禁用信息，LLM 收到后自行决策：
- 跳过该工具，用其他方式完成任务
- 告知用户该功能暂不可用
- 等待工具恢复后重试（仅流式模式下可能）

---

## 4. Skills（技能系统）

### 设计原则

- **按需加载**：System prompt 仅注入轻量描述索引，LLM 需要时通过工具获取完整指令
- **独立注册**：Skill 与 Tool 分开注册，各自职责清晰
- **文件驱动**：每个 Skill 是一个文件夹，包含 `SKILL.md`（必需）和脚本（可选）

### 目录结构

```
agent/skills/
  ├── base.py              # SkillBase 基类 + SkillRegistry
  └── <skill_name>/
      ├── SKILL.md         # 必须：## description + 详细说明
      └── *.py             # 可选：该 skill 需要的脚本
```

### SKILL.md 格式

```markdown
## description
简要描述这个 skill 做什么、什么场景触发（1-3 行）

## 详细说明
完整的执行规范、流程、约束...
```

- `## description` 到下一个 `##` 之间的内容作为轻量索引注入 system prompt
- `## description` 之后的所有内容（含后续 `##` 段）作为完整指令，通过工具返回

### SkillBase 基类

```python
class SkillBase(ABC):
    name: str                    # 文件夹名，如 "resume_gen"
    path: Path                   # skill 文件夹路径

    def get_description() -> str:
        """正则提取 ## description 到下一个 ## 之间的内容"""

    def get_full_prompt() -> str:
        """返回 SKILL.md 全文"""

    async def execute(**kwargs) -> str:
        """可选，有默认空实现。skill 有脚本时覆写"""
```

### SkillRegistry

独立于 `ToolRegistry`，启动时自动扫描 `agent/skills/*/SKILL.md`：

```python
class SkillRegistry:
    _skills: dict[str, SkillBase]

    def register(skill_folder: Path)    # 扫描文件夹，自动注册
    def get(name: str) -> SkillBase     # 按名称获取
    def get_all_descriptions() -> str   # 拼成 system prompt 用的索引文本
    def get_all_names() -> list[str]    # 所有已注册 skill 名称
```

### System Prompt 注入

```python
def build_static_prompt(work: str) -> str:
    parts = [STABLE_PROMPT]
    parts.append(get_role(work))           # 角色规则
    parts.append(_get_tools_description()) # 工具描述
    parts.append(_get_skills_description())# 🆕 Skill 索引
    parts.append(_get_user_md())           # USER.md
    return "\n\n---\n\n".join(parts)
```

注入的索引格式：

```markdown
## 可用 Skill
### resume_gen
描述：针对特定 JD 生成高匹配度中文简历，包含 STAR 格式、单页限制等规范

### match_score
描述：计算简历与 JD 的匹配度评分，包含技能、经验、学历、关键词四维度
```

### get_skill_prompt 工具

LLM 判断需要某个 Skill 时调用，获取完整指令：

```python
class GetSkillPromptTool(BaseTool):
    name = "get_skill_prompt"
    scenarios = []  # 通用，所有场景可用
    parameters = { "skill_name": { "type": "string", "description": "skill 名称" } }

    async def execute(self, skill_name: str, **kwargs) -> str:
        skill = skill_registry.get(skill_name)
        if not skill:
            return json.dumps({"error": f"未找到 skill: {skill_name}"})
        return skill.get_full_prompt()
```

### 完整流程

```
启动
  → SkillRegistry 自动扫描 agent/skills/*/SKILL.md
  → 每个文件夹实例化 SkillBase（或子类）
  → 注册到 skill_registry

用户请求
  → build_static_prompt() 注入 Skill 索引（轻量描述）
  → LLM 判断是否需要 Skill
      ├── 不需要 → 直接回答
      └── 需要 → 调用 get_skill_prompt(skill_name="xxx")
            → 返回 SKILL.md 全文
            → LLM 按指令执行
```

### 添加新 Skill

1. 在 `agent/skills/` 下创建文件夹（如 `resume_gen/`）
2. 编写 `SKILL.md`（必须包含 `## description` 段）
3. 添加脚本文件（可选）
4. 如有脚本，创建子类继承 `SkillBase`，覆写 `execute()`
5. 重启服务，自动注册

无需修改 Harness 核心代码。

---

## 5. Context（上下文管理）

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
│  - key_data (关键数据缓存)          │
├─────────────────────────────────────┤
│ Conversation Context (每轮更新)      │
│  - messages (对话历史)              │
│  - current_message                  │
└─────────────────────────────────────┘
```

### 消息构建流程

```python
def _build_messages(state: AgentState, message: str) -> list[dict]:
    messages = []

    # 1. System prompt (根据 scenario 动态构建)
    dynamic_context = {
        "key_data": state.key_data,  # 从 State 获取关键数据
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

#### 压缩守卫（Guard Conditions）

借鉴 Claude Code 的守卫机制，在以下场景**禁止触发压缩**：

```python
class CompressGuard:
    “””压缩守卫：防止递归压缩和状态污染”””

    def __init__(self):
        self._compressing = False       # 是否正在执行压缩
        self._tool_executing = False    # 是否正在执行工具
        self._streaming = False         # 是否正在流式响应

    # === 守卫 1: 防递归 ===
    # 压缩过程中会调用 LLM 生成摘要，如果摘要生成时又触发压缩检查，
    # 会导致无限递归。通过标记位阻止。
    def enter_compress(self):
        if self._compressing:
            raise RuntimeError(“检测到递归压缩，已阻止”)
        self._compressing = True

    def exit_compress(self):
        self._compressing = False

    def is_compressing(self) -> bool:
        return self._compressing

    # === 守卫 2: 防状态污染 ===
    # 工具执行中 / 流式响应写入中不触发压缩，
    # 避免替换 messages 时导致正在读写的管线数据不一致。
    def enter_tool_execution(self):
        self._tool_executing = True

    def exit_tool_execution(self):
        self._tool_executing = False

    def enter_streaming(self):
        self._streaming = True

    def exit_streaming(self):
        self._streaming = False

    def can_compress(self) -> bool:
        “””综合判断是否允许触发压缩”””
        if self._compressing:
            return False    # 守卫 1: 正在压缩中，防递归
        if self._tool_executing:
            return False    # 守卫 2a: 工具执行中，防状态污染
        if self._streaming:
            return False    # 守卫 2b: 流式响应中，防状态污染
        return True
```

**守卫状态机：**

```
空闲 ──用户请求──→ 处理中
  ↑                   │
  │                   ├──工具调用──→ 工具执行中（guard._tool_executing = True）
  │                   │                │
  │                   │                └──工具返回──→ 处理中
  │                   │
  │                   ├──流式响应──→ 流式写入中（guard._streaming = True）
  │                   │                │
  │                   │                └──流式结束──→ 空闲
  │                   │
  │                   └──达到阈值──→ 检查守卫
  │                                   │
  │                              can_compress()?
  │                               │          │
  │                              是         否
  │                               │          │
  │                               ▼          └──→ 跳过本轮，等下一轮检查
  └──────压缩完成──────────── 压缩中（guard._compressing = True）
```

#### 压缩流程（双层机制）

压缩系统分为两层，各司其职：

**第一层：滚动摘要（工作笔记）** — token 驱动，每消耗 10% 上下文窗口更新一次
**第二层：完整压缩（LLM 压缩）** — 75% 阈值触发，始终调用 LLM，滚动摘要作为辅助输入

```
每次工具调用完成后（Agent Loop 的每轮末尾）
    │
    ├─ 从 API 响应读取 usage，累加到 state.usage
    │
    ├─ 第一层：检查是否需要更新滚动摘要
    │   └─ should_update_summary(state)?
    │       ├─ 累计 token >= 下一个 10% 检查点 → update_summary()
    │       └─ 否 → 跳过
    │
    └─ 第二层：检查是否需要完整压缩
        └─ 估算 token >= 75% 阈值？
             │
            否 → 继续正常流程
            是 → 检查守卫 can_compress()
                  │
                 否 → 跳过本轮压缩
                 是 → 执行完整压缩（优先用滚动摘要，否则调 LLM）
```

#### 第一层：滚动摘要（工作笔记）

滚动摘要是上下文管理和记忆系统的**共同组件**（详见第 6 节 Memory）。它的核心作用是告诉压缩 LLM「什么内容是重要的」。

**数据流：**

```
上游: state.messages  ──→  滚动摘要 Hook  ──→  下游: 压缩 LLM
     (完整对话历史)         (state.summary)       (CompactHook._call_llm_compact)
```

- **上游**：`state.messages` — 完整对话历史，滚动摘要从中提取关键信息
- **下游**：压缩 LLM — 完整压缩时，滚动摘要作为辅助上下文注入压缩提示词

**触发机制：** 注册为 Hook（`compact_hook.py` 中的 `should_update_summary` / `update_summary`），每消耗上下文窗口的 10% token 触发一次（128k 窗口 → 每 ~12.8k tokens）。在 Agent Loop 每轮工具调用完成后检查。

```python
SUMMARY_TOKEN_RATIO = 0.10  # 每消耗 10% 上下文窗口更新一次

def should_update_summary(state, model):
    interval = int(CONTEXT_LIMITS[model] * SUMMARY_TOKEN_RATIO)
    total_tokens = state.usage.get(“total_tokens”, 0)
    next_checkpoint = state.summary_token_checkpoint + interval
    return total_tokens >= next_checkpoint
```

**摘要结构（固定模板）：**

```
【任务】{scenario}
【已完成】{已完成的关键步骤和结果}
【待完成】{当前阶段的目标}
【关键决策】{用户做出的不可逆选择}
【用户偏好】{用户表达的喜好/厌恶/风格倾向}
【重复工作流】{多次出现的工作模式，如"反复调整措辞（3次）"}
【重要发现】{对后续工作有价值的信息}
```

**新增维度说明：**

| 维度 | 记录什么 | 用途 |
|------|---------|------|
| 用户偏好 | 用户表达的喜好、厌恶、风格倾向 | 提炼到 Memory.md，跨会话保持 |
| 重复工作流 | 多次出现的工作模式（如"反复修改XX"） | 识别用户习惯，优化工作流 |
| 重要发现 | 对后续工作有价值的信息 | 避免重复发现，辅助决策 |

**工作笔记在上下文中的位置：**

```
[system prompt]                    ← 角色定义、工具描述
[工作笔记]                         ← state.summary，辅助上下文
[完整对话历史]                     ← 不替换，保留全部消息
[current user message]
```

#### 第二层：完整压缩（LLM 压缩）

当 token 达到 75% 阦值时触发完整压缩。**优先使用已有滚动摘要**，避免在高压下额外调用 LLM。

**LLM 收到的输入：**

```
[压缩提示词]                       ← COMPACT_PROMPT（结构化摘要要求）
[工作笔记]                         ← state.summary（滚动摘要，辅助参考）
[完整消息历史]                     ← 最近 20 条消息
```

**压缩后上下文组合：**

```
[system prompt]                    ← 原样保留
[“以下是之前对话的摘要：
  {LLM 生成的压缩摘要}” ]          ← LLM 基于完整历史 + 滚动摘要生成
[最近 3 轮的原始消息]               ← 保留短期上下文连贯
[current user message]            ← 新输入
```

**滚动摘要的角色：** 告诉压缩 LLM「什么内容是重要的」— 辅助 LLM 理解对话脉络、识别关键决策和未完成任务，提高压缩质量。LLM 读取的是完整历史，滚动摘要是额外的结构化提示。

#### 两层机制的协作时序

```
token 0%:     新会话，无摘要
token ~10%:   第一次更新滚动摘要（工作笔记）
token ~20%:   第二次更新滚动摘要
...
token ~70%:   第 N 次更新滚动摘要
token ~75%:   守卫检查通过 → 完整压缩
              → LLM 基于完整历史 + 滚动摘要生成压缩
              → 保留最近 3 轮 + 重置 token 计数
token ~85%:   压缩后第一次更新滚动摘要（重新开始计数）
...
```

#### 与旧方案对比

| 维度 | 旧方案（纯 LLM 压缩） | 新方案（双层机制） |
|---|---|---|
| 压缩时是否调用 LLM | 是（读全部历史生成摘要） | 是（完整历史 + 滚动摘要辅助） |
| 压缩失败风险 | 高（LLM 可能超限、格式错误） | 低（滚动摘要辅助，LLM 有更充分的上下文） |
| 信息保留质量 | 取决于 LLM 一次性摘要能力 | 滚动摘要持续更新，质量更稳定 |
| 额外 token 消耗 | 每次压缩消耗一次 LLM 调用 | 每 10% token 更新滚动摘要 + 压缩时一次 LLM 调用 |

#### 与 Agent 循环的集成

```python
# agent/core/baseagent.py 中的核心循环

async def run(self, user_message: str) -> dict:
    self.state.add_message(“user”, user_message)

    # 第二层：检查是否需要完整压缩（75% 阈值）
    if await self._compact_hook.should_trigger(self.state):
        self.state = await self._compact_hook.execute(self.state)

    messages = self._build_messages(user_message)

    for _ in range(self.max_rounds):
        choice = await self._call_llm(messages)
        # ... 处理工具调用 ...

        # 第一层：检查是否需要更新滚动摘要（10% token 驱动）
        if should_update_summary(self.state, model):
            await update_summary(self.state, model)

        messages = self._build_messages(user_message)
```

#### 前端交互

- 压缩对用户**完全透明**（自动执行，无感知）
- 不展示 usage 信息（目标用户非开发者）
- 无压缩失败提示（滚动摘要兜底，机械截断不会失败）

---

## 6. Memory（记忆系统）

### 设计原则

- **自进化记忆**：Agent 通过滚动摘要识别值得持久化的信息，自动提炼到 Memory.md
- **冻结快照**：Memory.md 在会话开始时注入 system prompt，会话中不刷新（保留前缀缓存）
- **SQLite 持久化**：单文件数据库（`data/app.db`），零配置，支持断线重连和跨天恢复
- **滚动摘要是上下文管理和记忆系统的共同部分**（见下方"滚动摘要"小节）

### 记忆类型

```
Memory
├── Short-term (短期，当前会话)
│   ├── messages              # 完整对话历史
│   └── turn_count            # 当前轮次
│
├── Working (工作记忆，关键数据缓存)
│   └── key_data              # 通用关键数据缓存
│       ├── "parse_jd"        # JD 解析结果
│       ├── "parse_resume"    # 简历解析结果
│       └── ...               # 其他工具结果
│
├── Rolling Summary (滚动摘要，跨层共享)
│   └── summary               # 滚动摘要（工作笔记）
│
├── Memory.md (持久化记忆，自进化)
│   ├── 用户偏好              # 喜好、厌恶、风格倾向
│   ├── 工作习惯              # 重复工作流、习惯模式
│   ├── 项目约定              # 规则、格式要求
│   └── 关键教训              # 从错误中学到的经验
│
└── Persistent (持久化，SQLite)
    ├── agent_sessions 表     # 会话级状态（messages、key_data、summary）
    └── agent_loop_state 表   # 循环级状态（usage、summary_token_checkpoint）
```

### 自进化记忆系统（Memory.md）

#### 定义

Memory.md 是跨会话持久化的记忆文件，由 Agent 自动维护（非用户手动编辑），存储提炼后的精华信息。

#### 存储内容

| 类别 | 记录什么 | 示例 |
|------|---------|------|
| 用户偏好 | 喜好、厌恶、风格倾向 | "喜欢简洁风格，不喜欢过度包装" |
| 工作习惯 | 重复工作流、习惯模式 | "修改简历时会反复打磨措辞" |
| 项目约定 | 规则、格式要求 | "简历单页、STAR格式" |
| 关键教训 | 从错误/纠正中学到的 | "成果描述要符合实际" |

#### 字符限制

- 上限：2,200 字符（约 800 tokens）
- 典型条目数：8-15 条
- 超限时：整合或替换现有条目

#### 提炼机制

从滚动摘要提炼到 Memory.md 的三种触发方式：

| 触发条件 | 动作 | 说明 |
|---------|------|------|
| 滚动摘要更新计数 % 2 == 0 | 从摘要提炼 | 每两次滚动摘要更新触发一次 |
| 会话结束 / 压缩前 | 识别一次 | 最后机会提炼 |
| 用户关键词 | 直接触发 | "记住"、"以后都..."、"不要..." |

**提炼流程：**

```
滚动摘要更新
    │
    ├─ 更新计数 +1
    │
    └─ 计数 % 2 == 0?
         │
         是 → 调用轻量 LLM 提炼
              │
              ├─ 识别滚动摘要中的持久化内容
              │   - 用户偏好
              │   - 重复工作流
              │   - 关键教训
              │
              ├─ 检查 Memory.md 容量
              │   ├─ 有空间 → add 新条目
              │   └─ 已满 → replace 整合旧条目
              │
              └─ 写入 Memory.md（磁盘持久化）
```

**提炼 Prompt（轻量模型）：**

```
你是记忆提炼助手。从以下滚动摘要中识别值得跨会话持久化的信息。

**值得记录**：
- 用户明确表达的偏好/厌恶
- 多次出现的工作模式
- 用户纠正过的错误（避免再犯）
- 明确的项目约定/规则

**不值得记录**：
- 临时任务状态
- 容易重新发现的事实
- 一次性的上下文信息

当前 Memory.md：
{current_memory}

滚动摘要：
{rolling_summary}

输出格式（如有新内容）：
[CATEGORY] 内容

CATEGORY: 用户偏好 | 工作习惯 | 项目约定 | 关键教训
```

#### memory 工具

Agent 通过 memory 工具管理 Memory.md：

```python
class MemoryTool(BaseTool):
    name = "memory"
    description = "管理持久化记忆（Memory.md）"
    parameters = {
        "action": {
            "type": "string",
            "enum": ["add", "replace", "remove"],
            "description": "操作类型"
        },
        "target": {
            "type": "string",
            "description": "目标类别：用户偏好 | 工作习惯 | 项目约定 | 关键教训"
        },
        "content": {
            "type": "string",
            "description": "记忆内容（add/replace 时必填）"
        },
        "old_text": {
            "type": "string",
            "description": "要替换/删除的子字符串（replace/remove 时必填）"
        }
    }
```

**操作说明：**

| 操作 | 参数 | 说明 |
|------|------|------|
| add | target, content | 添加新条目到指定类别 |
| replace | target, old_text, content | 用新内容替换匹配的旧条目 |
| remove | target, old_text | 删除匹配的条目 |

**触发场景：**
- 用户说"记住这个"、"以后都..."、"不要..." → Agent 调用 memory 工具
- 自动提炼流程中识别到持久化内容 → Agent 调用 memory 工具

### 滚动摘要（Rolling Summary）

滚动摘要是上下文管理（Context）和记忆系统（Memory）的**共同组件**，承担信息桥梁的角色。

**核心作用：** 告诉压缩 LLM「什么内容是重要的」。当 75% 阈值触发完整压缩时，滚动摘要作为辅助输入传递给压缩 LLM，帮助它理解对话脉络、识别关键决策和未完成任务，从而生成更高质量的压缩摘要。

**架构定位：**

```
上游                    滚动摘要                    下游
state.messages  ──→  RollingSummaryHook  ──→  压缩 LLM（CompactHook）
(完整对话历史)         (摘要 state.summary)       (生成压缩摘要)
```

- **上游**：`state.messages` — 完整对话历史，滚动摘要从中提取关键信息
- **下游**：压缩 LLM — 完整压缩时，滚动摘要作为辅助上下文注入压缩提示词

**触发机制：** 每消耗上下文窗口的 10% token 更新一次（128k 窗口 → 每 ~12.8k tokens），基于 `state.usage["total_tokens"]` 累计值和 `state.summary_token_checkpoint` 检查点驱动。

**实现：** 注册为 Hook（`compact_hook.py` 中的 `should_update_summary` / `update_summary`），在 Agent Loop 每轮工具调用完成后检查并执行。与 `CompactHook`（完整压缩）共享守卫机制和 token 计数基础设施。

### 会话持久化（Session Persistence）

**定义：** 完整会话的保存、恢复、删除，以及跨会话的状态管理。

#### 存储结构

```sql
-- 会话级状态（由 snapshot_session() 写入）
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,           -- session_id (UUID)
    user_id INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    title TEXT DEFAULT '',
    messages TEXT NOT NULL DEFAULT '[]',      -- JSON 字符串
    key_data TEXT DEFAULT '{}',               -- JSON 字符串（原 tool_results）
    uploaded_file_ids TEXT DEFAULT '[]',      -- JSON 字符串
    summary TEXT DEFAULT '',                  -- 滚动摘要
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 循环级状态（由 snapshot_loop() 写入）
CREATE TABLE agent_loop_state (
    session_id TEXT PRIMARY KEY,   -- 关联 agent_sessions.id
    usage TEXT DEFAULT '{}',                   -- JSON 字符串（累计 token）
    summary_token_checkpoint INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
);
```

#### 数据治理

- 每用户每场景最多保留 10 个会话，`save_session()` 时自动清理最旧记录
- `messages` 使用 TEXT 列（64KB 上限），压缩机制在 75% 阈值触发，实际不会触及上限

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
保存到 DB：AgentState.snapshot_session() → agent_sessions 表
           AgentState.snapshot_loop() → agent_loop_state 表
    ↓
返回响应 + session_id
```

---

## 7. Agent 配置

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

## 8. 执行流程

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
    ├── 加载 Prompt (build_system_prompt，含 Skill 索引)
    ├── 加载 Tools (get_all_tools，含 get_skill_prompt)
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
保存 State 到 DB（snapshot_session + snapshot_loop）
    ↓
返回结果 + session_id
```

---

## 9. 扩展新 Agent

只需 3 步：

1. **添加角色定义**：在 `prompts/roles.py` 的 `ROLES` 字典中添加新场景
2. **添加动态模板**（可选）：在 `prompts/dynamic.py` 的 `DYNAMIC_TEMPLATES` 中添加
3. **添加路由**（如需要）：`routers/new_agent.py`

无需修改 Harness 核心代码。

### 添加新工具

1. 在 `tools/` 下创建新工具类，继承 `BaseTool`
2. 实现必要的属性和方法
3. 调用 `registry.register()` 注册

### 添加新 Skill

1. 在 `agent/skills/` 下创建文件夹（如 `resume_gen/`）
2. 编写 `SKILL.md`（必须包含 `## description` 段）
3. 添加脚本文件（可选）
4. 如有脚本，创建子类继承 `SkillBase`，覆写 `execute()`
5. 重启服务，自动注册

无需修改 Harness 核心代码。

---

## 10. API 调用示例

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
    "key_data": {"parse_jd": jd_data, "parse_resume": resume_data},
})

# 面试场景
interview_prompt = build_system_prompt("interview", {
    "key_data": {"parse_resume": resume_data},
})
```

### 会话持久化

```python
from agent.core.state import AgentState

# 从 DB 加载
state = AgentState.restore(db_data)

# 保存到 DB
session_snapshot = state.snapshot_session()  # 写入 agent_sessions 表
loop_snapshot = state.snapshot_loop()        # 写入 agent_loop_state 表
```
