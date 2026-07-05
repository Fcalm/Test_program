"""CompactHook 压缩流程测试"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from agent.core.state import AgentState
from agent.hooks.compact_hook import (
    CompactHook,
    CompactError,
    count_tokens,
    get_context_limit,
    estimate_compact_space,
    COMPACT_THRESHOLD,
    COMPACT_MAX_RETRIES,
)


# === 辅助函数 ===

def _make_messages(n: int, content_len: int = 100) -> list[dict]:
    """生成 n 条模拟消息"""
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg_{i} " * (content_len // 6)}
        for i in range(n)
    ]


def _make_state(messages: list[dict] | None = None, **kwargs) -> AgentState:
    """创建测试用 AgentState"""
    return AgentState(
        session_id="test-session",
        user_id=1,
        scenario="resume",
        messages=messages or [],
        **kwargs,
    )


# === count_tokens 测试 ===

class TestCountTokens:
    """测试 token 计数"""

    def test_empty_messages(self):
        assert count_tokens([]) == 0

    def test_basic_counting(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = count_tokens(msgs)
        # 每条消息 4 开销 + content tokens
        assert result > 4

    def test_tool_calls_counted(self):
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "t1", "function": {"name": "foo", "arguments": "{}"}}],
        }]
        result = count_tokens(msgs)
        assert result > 4  # 开销 + tool_call tokens

    def test_tool_role_counted(self):
        msgs = [{"role": "tool", "content": '{"result": "ok"}'}]
        result = count_tokens(msgs)
        assert result > 4

    def test_fallback_without_tiktoken(self):
        """tiktoken 不可用时降级为字符计数"""
        import builtins
        real_import = builtins.__import__

        def _no_tiktoken(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError("no tiktoken")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_no_tiktoken):
            msgs = [{"role": "user", "content": "a" * 100}]
            result = count_tokens(msgs)
        # 降级：sum of len(str(content)) = 100
        assert result == 100


# === get_context_limit 测试 ===

class TestGetContextLimit:
    """测试模型上下文限制查询"""

    def test_known_model(self):
        assert get_context_limit("deepseek-v4-flash") == 128_000

    def test_another_known_model(self):
        assert get_context_limit("deepseek-v4-pro") == 200_000

    def test_unknown_model_defaults(self):
        assert get_context_limit("gpt-4") == 128_000


# === estimate_compact_space 测试 ===

class TestEstimateCompactSpace:
    """测试压缩空间估算"""

    def test_short_messages(self):
        msgs = _make_messages(3, content_len=10)
        result = estimate_compact_space(msgs)
        # 摘要 300 + 最近 3 条 tokens
        assert result >= 300

    def test_long_messages_takes_recent_6(self):
        msgs = _make_messages(20, content_len=100)
        result = estimate_compact_space(msgs)
        # 只取最近 6 条
        assert result >= 300


# === should_trigger 测试 ===

class TestShouldTrigger:
    """测试压缩触发判断"""

    @pytest.mark.asyncio
    async def test_too_few_messages(self):
        """消息数 < 6 不触发"""
        hook = CompactHook()
        state = _make_state(_make_messages(5))
        assert await hook.should_trigger(state) is False

    @pytest.mark.asyncio
    async def test_below_threshold(self):
        """token 未达阈值不触发"""
        hook = CompactHook()
        # 6 条短消息，token 远低于 75%
        state = _make_state(_make_messages(6, content_len=10))
        assert await hook.should_trigger(state) is False

    @pytest.mark.asyncio
    async def test_above_threshold(self):
        """token 达到阈值触发"""
        hook = CompactHook()
        msgs = _make_messages(6, content_len=10)
        state = _make_state(msgs)
        # mock count_tokens 返回超阈值值
        threshold = int(get_context_limit(hook._model) * COMPACT_THRESHOLD)
        with patch("agent.hooks.compact_hook.count_tokens", return_value=threshold + 1):
            assert await hook.should_trigger(state) is True


# === _create_compacted_state 测试 ===

class TestCreateCompactedState:
    """测试压缩状态创建"""

    def test_keeps_recent_6_messages(self):
        """保留最近 6 条消息"""
        hook = CompactHook()
        old_state = _make_state(_make_messages(20))
        new_state = hook._create_compacted_state(old_state, "摘要内容")

        assert len(new_state.messages) == 6

    def test_filters_system_messages(self):
        """过滤 system 消息"""
        hook = CompactHook()
        msgs = _make_messages(4)
        # 在最近 6 条中插入 system 消息
        msgs.append({"role": "system", "content": "旧 system"})
        msgs.append({"role": "user", "content": "最新消息"})
        old_state = _make_state(msgs)
        new_state = hook._create_compacted_state(old_state, "摘要")

        # system 消息应被过滤
        for msg in new_state.messages:
            assert msg["role"] != "system"

    def test_summary_stored_in_key_data(self):
        """摘要存入 key_data["_compact_summary"]"""
        hook = CompactHook()
        old_state = _make_state(_make_messages(10))
        new_state = hook._create_compacted_state(old_state, "这是摘要")

        assert new_state.key_data["_compact_summary"] == "这是摘要"

    def test_preserves_existing_key_data(self):
        """保留已有的 key_data"""
        hook = CompactHook()
        old_state = _make_state(
            _make_messages(10),
            key_data={"parse_jd": {"position": "工程师"}},
        )
        new_state = hook._create_compacted_state(old_state, "摘要")

        assert new_state.key_data["parse_jd"]["position"] == "工程师"
        assert "_compact_summary" in new_state.key_data

    def test_preserves_session_identity(self):
        """保留 session_id, user_id, scenario"""
        hook = CompactHook()
        old_state = _make_state(_make_messages(10))
        new_state = hook._create_compacted_state(old_state, "摘要")

        assert new_state.session_id == old_state.session_id
        assert new_state.user_id == old_state.user_id
        assert new_state.scenario == old_state.scenario

    def test_compact_count_reset(self):
        """压缩成功后 compact_count 归 0"""
        hook = CompactHook()
        old_state = _make_state(_make_messages(10))
        old_state.compact_count = 2
        new_state = hook._create_compacted_state(old_state, "摘要")

        assert new_state.compact_count == 0

    def test_short_history_keeps_all(self):
        """历史消息 < 6 条时全部保留（过滤 system 后）"""
        hook = CompactHook()
        msgs = _make_messages(4)
        old_state = _make_state(msgs)
        new_state = hook._create_compacted_state(old_state, "摘要")

        assert len(new_state.messages) == 4


# === _handle_failure 测试 ===

class TestHandleFailure:
    """测试失败处理"""

    def test_increments_compact_count(self):
        hook = CompactHook()
        state = _make_state(_make_messages(10))
        hook._handle_failure(state)
        assert state.compact_count == 1

    def test_raises_compact_error_at_limit(self):
        """compact_count 超过上限时抛出 CompactError"""
        hook = CompactHook()
        state = _make_state(_make_messages(10))
        state.compact_count = COMPACT_MAX_RETRIES

        with pytest.raises(CompactError, match="超限"):
            hook._handle_failure(state)

    def test_discards_messages_when_space_low(self):
        """空间不足时丢弃最早 10% 消息"""
        hook = CompactHook()
        # 100 条消息，应丢弃 10 条
        msgs = _make_messages(100, content_len=4000)
        state = _make_state(msgs)
        original_count = len(state.messages)

        hook._handle_failure(state)

        assert len(state.messages) < original_count
        assert len(state.messages) == 90  # 100 - 10


# === execute 测试（mock LLM） ===

class TestExecute:
    """测试完整压缩流程"""

    @pytest.mark.asyncio
    async def test_success_creates_new_state(self):
        """成功压缩后返回新 state"""
        hook = CompactHook()
        state = _make_state(_make_messages(20))

        with patch.object(hook, "_call_llm_compact", new_callable=AsyncMock, return_value="压缩摘要"):
            new_state = await hook.execute(state)

        assert new_state is not state
        assert "_compact_summary" in new_state.key_data
        assert new_state.key_data["_compact_summary"] == "压缩摘要"

    @pytest.mark.asyncio
    async def test_failure_retries_then_raises(self):
        """失败超过上限后抛出 CompactError"""
        hook = CompactHook()
        state = _make_state(_make_messages(10))
        # 预设 compact_count 接近上限
        state.compact_count = COMPACT_MAX_RETRIES - 1

        call_count = 0

        async def _failing_compact(s):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("LLM 挂了")

        with patch.object(hook, "_call_llm_compact", side_effect=_failing_compact):
            with pytest.raises(CompactError):
                await hook.execute(state)

        # 应重试 COMPACT_MAX_RETRIES 次后中断
        assert call_count == 2  # 第一次失败 +1 = 上限，第二次失败抛异常

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """第一次失败，第二次成功"""
        hook = CompactHook()
        state = _make_state(_make_messages(20))

        call_count = 0

        async def _flaky_compact(s):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("网络抖动")
            return "重试后的摘要"

        with patch.object(hook, "_call_llm_compact", side_effect=_flaky_compact):
            new_state = await hook.execute(state)

        assert call_count == 2
        assert new_state.key_data["_compact_summary"] == "重试后的摘要"


# === _build_messages 集成测试 ===

class TestBuildMessagesWithSummary:
    """测试 _build_messages 中的压缩摘要合并"""

    def test_summary_merged_into_system_prompt(self):
        """压缩摘要合并到 system prompt 末尾"""
        from agent.core.baseagent import BaseAgent

        agent = BaseAgent(scenario="resume")
        agent.state.key_data["_compact_summary"] = "用户想生成简历"

        messages = agent._build_messages("你好")

        # 应只有一条 system message
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1

        # system prompt 应包含摘要
        assert "[对话摘要]" in system_msgs[0]["content"]
        assert "用户想生成简历" in system_msgs[0]["content"]

    def test_no_summary_no_extra_content(self):
        """无压缩摘要时 system prompt 不含 [对话摘要]"""
        from agent.core.baseagent import BaseAgent

        agent = BaseAgent(scenario="resume")

        messages = agent._build_messages("你好")

        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "[对话摘要]" not in system_msgs[0]["content"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# === AgentState.restore 校验测试 ===

class TestRestoreValidation:
    """测试 restore() 数据完整性校验"""

    def test_valid_data(self):
        """正常数据恢复成功"""
        data = {
            "session_id": "abc-123",
            "user_id": 1,
            "scenario": "resume",
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
            ],
        }
        state = AgentState.restore(data)
        assert state.session_id == "abc-123"
        assert len(state.messages) == 2

    def test_missing_session_id_raises(self):
        """缺少 session_id 抛出 ValueError"""
        data = {"messages": []}
        with pytest.raises(ValueError, match="session_id"):
            AgentState.restore(data)

    def test_empty_session_id_raises(self):
        """空 session_id 抛出 ValueError"""
        data = {"session_id": "", "messages": []}
        with pytest.raises(ValueError, match="session_id"):
            AgentState.restore(data)

    def test_messages_not_list_raises(self):
        """messages 非 list 类型抛出 ValueError"""
        data = {"session_id": "abc", "messages": "not a list"}
        with pytest.raises(ValueError, match="messages 类型错误"):
            AgentState.restore(data)

    def test_message_missing_role_raises(self):
        """消息缺少 role 字段抛出 ValueError"""
        data = {
            "session_id": "abc",
            "messages": [{"content": "hello"}],
        }
        with pytest.raises(ValueError, match="缺少 role"):
            AgentState.restore(data)

    def test_message_not_dict_raises(self):
        """消息元素非 dict 类型抛出 ValueError"""
        data = {
            "session_id": "abc",
            "messages": ["not a dict"],
        }
        with pytest.raises(ValueError, match="类型错误"):
            AgentState.restore(data)

    def test_compact_count_always_zero_after_restore(self):
        """compact_count 不从 DB 恢复，每次请求重置为 0"""
        data = {
            "session_id": "abc",
            "messages": [],
            "compact_count": 2,
        }
        state = AgentState.restore(data)
        assert state.compact_count == 0

    def test_compact_count_defaults_zero(self):
        """compact_count 缺失时默认为 0"""
        data = {"session_id": "abc", "messages": []}
        state = AgentState.restore(data)
        assert state.compact_count == 0


# === 熔断器测试 ===

class TestCircuitBreaker:
    """测试 ToolRegistry 按场景熔断器"""

    def setup_method(self):
        from agent.tools.registry import ToolRegistry
        self.registry = ToolRegistry()

    def test_not_disabled_initially(self):
        assert self.registry.is_disabled("some_tool", "resume") is False

    def test_failure_count_increments(self):
        self.registry.record_failure("tool_a", "resume")
        assert self.registry.is_disabled("tool_a", "resume") is False
        self.registry.record_failure("tool_a", "resume")
        assert self.registry.is_disabled("tool_a", "resume") is False
        self.registry.record_failure("tool_a", "resume")
        assert self.registry.is_disabled("tool_a", "resume") is True

    def test_per_scenario_isolation(self):
        """同一工具在不同场景独立熔断"""
        for _ in range(3):
            self.registry.record_failure("tool_a", "resume")
        assert self.registry.is_disabled("tool_a", "resume") is True
        assert self.registry.is_disabled("tool_a", "interview") is False

    def test_success_resets_count(self):
        self.registry.record_failure("tool_a", "resume")
        self.registry.record_failure("tool_a", "resume")
        self.registry.record_success("tool_a", "resume")
        self.registry.record_failure("tool_a", "resume")
        # 成功重置后，只失败 1 次，不应触发
        assert self.registry.is_disabled("tool_a", "resume") is False

    def test_cooldown_expires(self):
        """冷却期过后自动恢复"""
        import time
        from agent.tools.registry import CIRCUIT_BREAKER_COOLDOWN

        for _ in range(3):
            self.registry.record_failure("tool_a", "resume")
        assert self.registry.is_disabled("tool_a", "resume") is True

        # 模拟冷却期过
        self.registry._disabled_until[("tool_a", "resume")] = time.time() - 1
        assert self.registry.is_disabled("tool_a", "resume") is False

    def test_reset_circuit_breaker(self):
        for _ in range(3):
            self.registry.record_failure("tool_a", "resume")
        self.registry.reset_circuit_breaker("tool_a", "resume")
        assert self.registry.is_disabled("tool_a", "resume") is False

    def test_disabled_tool_excluded_from_scenario(self):
        """熔断工具不出现在 get_tools_by_scenario 中"""
        # 需要注册一个真实工具
        from agent.tools.basetool import BaseTool

        class DummyTool(BaseTool):
            @property
            def name(self): return "dummy"
            @property
            def description(self): return "test"
            @property
            def parameters(self): return {"type": "object", "properties": {}}
            @property
            def max_results_chars(self): return 1000
            async def execute(self, **kwargs): return "ok"

        self.registry.register(DummyTool)
        assert "dummy" in self.registry.get_tools_by_scenario("resume")

        for _ in range(3):
            self.registry.record_failure("dummy", "resume")
        assert "dummy" not in self.registry.get_tools_by_scenario("resume")


# === _execute_tool 测试 ===

class TestExecuteTool:
    """测试 BaseAgent._execute_tool 重试 + 截断"""

    @pytest.mark.asyncio
    async def test_success_returns_result(self):
        from agent.core.baseagent import BaseAgent

        agent = BaseAgent(scenario="resume")

        tool = MagicMock()
        tool.name = "test_tool"
        tool.max_results_chars = 1000
        tool.execute = AsyncMock(return_value='{"success": true}')

        result = await agent._execute_tool(tool, {})
        assert '{"success": true}' in result

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        from agent.core.baseagent import BaseAgent

        agent = BaseAgent(scenario="resume")

        tool = MagicMock()
        tool.name = "test_tool"
        tool.max_results_chars = 1000
        call_count = 0

        async def _flaky(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return '{"success": true}'

        tool.execute = _flaky

        with patch("agent.core.baseagent.asyncio.sleep", new_callable=AsyncMock):
            result = await agent._execute_tool(tool, {})

        assert call_count == 3
        assert '{"success": true}' in result

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        from agent.core.baseagent import BaseAgent

        agent = BaseAgent(scenario="resume")

        tool = MagicMock()
        tool.name = "failing_tool"
        tool.max_results_chars = 1000
        tool.execute = AsyncMock(side_effect=RuntimeError("broken"))

        with patch("agent.core.baseagent.asyncio.sleep", new_callable=AsyncMock):
            result = await agent._execute_tool(tool, {})

        assert "执行失败" in result
        assert "3 次" in result

    @pytest.mark.asyncio
    async def test_truncation(self):
        from agent.core.baseagent import BaseAgent

        agent = BaseAgent(scenario="resume")

        tool = MagicMock()
        tool.name = "test_tool"
        tool.max_results_chars = 50
        tool.execute = AsyncMock(return_value="x" * 200)

        result = await agent._execute_tool(tool, {})
        assert len(result) < 200
        assert "截断" in result
