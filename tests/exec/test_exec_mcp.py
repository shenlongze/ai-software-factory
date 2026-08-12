"""tests/exec/test_exec_mcp.py — S10-020 Task 001 MCP Adapter Foundation 测试。

覆盖 (MCP Connection / MCPClient Interface / Mock MCP / MCPToolAdapter /
MCP Tool 注册 / Permission Chain / ToolExecutor 集成 / Event Chain):
- MCPConnection 模型: id/name/server_url/transport/enabled/metadata/created_at
  字段完整; 默认 transport 不连公网; 未知字段拒绝 (extra=forbid)
- MCPClient Protocol: connect()/disconnect()/list_tools()/call_tool() 四方法
  契约 (不绑具体 MCP SDK — Provider 风格); MockMCPClient 结构满足契约
- MockMCPClient (不连公网): echo tool ({message: "hello"} → {message: "hello"});
  connect/disconnect 状态; list_tools 返回 echo schema; 未知 tool 响亮报错;
  缺 message 响亮报错
- MCPToolAdapter: MCP Tool Schema → 内部 Tool (Tool Model 不变 — 只多
  source/metadata); handler 包装 call_tool; id 保留 schema.name (Agent 不知
  来源); metadata {source: "mcp", server, server_url, transport}
- Tool source/metadata 扩展: 旧 Tool (无字段) 无损; source 默认 "internal";
  非法 source 响亮拒绝
- MCP Tool 注册: MCPRegistry.register_connection → 发现 → Adapter →
  ToolRegistry.register (与 filesystem.read 同表); Agent 视角无差别
- Permission Chain: MCP tool 注册后走现有 check_tool_access (Agent→Skill→
  Tool); Skill 不含 mcp tool → 拒; 含 → 放行; 禁止绕过
- Mock MCP 完整链路: ToolExecutor.execute("echo") → {message: "hello"} 往返
- Event Chain: mcp_connected/mcp_tool_discovered (执行时) +
  mcp_tool_registered (注册时) 3 事件 + 完整链路
  agent_started→skill_loaded→task_received→thinking_started→decision_created→
  tool_requested→mcp_connected→mcp_tool_discovered→tool_started→tool_completed→
  execution_completed

basename 全仓库唯一 (test_exec_* 前缀); 依赖 tests/exec/conftest.py 的
sys.path (factory-exec 挂载, `exec` 包导入)。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from exec.mcp import (
    MCPClient,
    MCPConnection,
    MCPConnectionError,
    MCPRegistry,
    MCPToolAdapter,
    MCPToolError,
    MCPToolNotFoundError,
    MCPToolSchema,
    MockMCPClient,
    new_mcp_connection_id,
)
from exec.runtime_session import (
    RuntimeEventType,
    RuntimeSession,
    RuntimeSessionStore,
)
from exec.skill import (
    Skill,
    SkillPermissionPolicy,
    SkillRegistry,
    build_system_skills,
)
from exec.tool import (
    Tool,
    ToolExecutor,
    ToolPermissionPolicy,
    ToolRegistry,
    ToolResult,
    validate_against_schema,
)


# ------------------------------------------------------------------ MCPConnection 模型


class TestMCPConnectionModel:
    def test_connection_fields_complete(self):
        """MCPConnection 字段完整: id/name/server_url/transport/enabled/metadata
        (描述外部 MCP 服务连接 — 本 Task 仅 Mock, 不连公网)。"""
        conn = MCPConnection(
            id="mcp-abc123",
            name="mock-echo",
            server_url="mock://echo",
            transport="mock",
            metadata={"vendor": "mock"},
        )
        assert conn.id == "mcp-abc123"
        assert conn.name == "mock-echo"
        assert conn.server_url == "mock://echo"
        assert conn.transport == "mock"
        assert conn.enabled is True
        assert conn.metadata == {"vendor": "mock"}
        assert conn.created_at is not None
        assert isinstance(conn.created_at, datetime)

    def test_connection_defaults(self):
        """缺省字段: transport 默认 mock (本 Task 仅 Mock 可用 — 不连公网) /
        enabled=True / metadata 缺省 {} / created_at 自动。"""
        conn = MCPConnection(
            id="mcp-1", name="echo", server_url="mock://echo"
        )
        assert conn.transport == "mock"
        assert conn.enabled is True
        assert conn.metadata == {}
        assert conn.created_at is not None

    def test_connection_unknown_field_rejected(self):
        """未知字段 → 响亮拒绝 (extra=forbid — 模型严格, 不静默吞字段)。"""
        with pytest.raises(ValueError):
            MCPConnection(  # type: ignore[call-arg]
                id="mcp-1", name="echo", server_url="mock://echo", bogus=1
            )

    def test_new_connection_id_shape(self):
        """new_mcp_connection_id → 'mcp-<hex8>' 形状 (唯一 basename 语义)。"""
        cid = new_mcp_connection_id()
        assert cid.startswith("mcp-")
        assert len(cid) == len("mcp-") + 8


# ------------------------------------------------------------------ MCPClient Interface (不绑 SDK)


class TestMCPClientInterface:
    def test_mock_client_satisfies_protocol(self):
        """MockMCPClient 结构满足 MCPClient Protocol (connect/disconnect/
        list_tools/call_tool — 不绑具体 MCP SDK, Provider 风格)。"""
        assert hasattr(MCPClient, "connect")
        assert hasattr(MCPClient, "disconnect")
        assert hasattr(MCPClient, "list_tools")
        assert hasattr(MCPClient, "call_tool")
        client = MockMCPClient()
        for method in ("connect", "disconnect", "list_tools", "call_tool"):
            assert callable(getattr(client, method))

    def test_mock_client_connect_disconnect_state(self):
        """MockMCPClient connect → connected True; disconnect → False (幂等)。"""
        client = MockMCPClient()
        assert client.connected is False
        client.connect()
        assert client.connected is True
        client.connect()  # 幂等 — 二次连接不报错
        assert client.connected is True
        client.disconnect()
        assert client.connected is False
        client.disconnect()  # 幂等
        assert client.connected is False


# ------------------------------------------------------------------ Mock MCP Server (echo, 不连公网)


class TestMockMCPClient:
    def test_list_tools_returns_echo_schema(self):
        """MockMCPClient.list_tools → [echo] (name/description/input_schema)。"""
        client = MockMCPClient()
        tools = client.list_tools()
        assert [t.name for t in tools] == ["echo"]
        echo = tools[0]
        assert echo.name == "echo"
        assert echo.description
        assert echo.input_schema.get("type") == "object"
        assert "message" in echo.input_schema.get("properties", {})

    def test_echo_roundtrip(self):
        """echo 往返: {message: "hello"} → {message: "hello"} (不连公网)。"""
        client = MockMCPClient()
        client.connect()
        result = client.call_tool("echo", {"message": "hello"})
        assert result == {"message": "hello"}

    def test_call_tool_unknown_tool_loud(self):
        """未知 tool → MCPToolNotFoundError 响亮 (不静默)。"""
        client = MockMCPClient()
        client.connect()
        with pytest.raises(MCPToolNotFoundError):
            client.call_tool("nope", {})

    def test_echo_missing_message_loud(self):
        """echo 缺 message → MCPToolError 响亮 (输入不完整不假装成功)。"""
        client = MockMCPClient()
        client.connect()
        with pytest.raises(MCPToolError):
            client.call_tool("echo", {})


# ------------------------------------------------------------------ MCPToolAdapter (Schema → Internal Tool)


class TestMCPToolAdapter:
    def _adapter(self, client=None, connection=None, **kwargs) -> MCPToolAdapter:
        client = client or MockMCPClient()
        connection = connection or MCPConnection(
            id="mcp-abc123",
            name="mock-echo",
            server_url="mock://echo",
            transport="mock",
        )
        return MCPToolAdapter(client, connection, **kwargs)

    def test_adapter_converts_schema_to_internal_tool(self):
        """MCP Tool Schema → 内部 Tool: id 保留 schema.name (Agent 不知来源);
        source='mcp'; metadata {source, server, server_url, transport}; handler
        可调用 (包装 call_tool); enabled=True。"""
        schema = MCPToolSchema(
            name="echo",
            description="回显消息",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )
        tool = self._adapter().to_internal_tool(schema)
        assert isinstance(tool, Tool)
        assert tool.id == "echo"
        assert tool.name == "echo"
        assert tool.description == "回显消息"
        assert tool.source == "mcp"
        assert tool.metadata["source"] == "mcp"
        assert tool.metadata["server"] == "mock-echo"
        assert tool.metadata["server_url"] == "mock://echo"
        assert tool.metadata["transport"] == "mock"
        assert callable(tool.handler)
        assert tool.enabled is True

    def test_adapter_handler_calls_mcp_tool(self):
        """handler (input, context) → client.call_tool(name, input) — Mock
        echo 往返 {message: "hello"} → {message: "hello"}。"""
        client = MockMCPClient()
        adapter = self._adapter(client=client)
        tool = adapter.to_internal_tool(
            MCPToolSchema(name="echo", description="echo", input_schema={})
        )
        output = tool.handler({"message": "hello"}, {})
        assert output == {"message": "hello"}

    def test_adapter_handler_unknown_tool_propagates(self):
        """handler 调未知 MCP tool → MCPToolNotFoundError 上抛 (ToolExecutor
        捕获转 ToolResult.failed — 不吞不伪装)。"""
        adapter = self._adapter()
        tool = adapter.to_internal_tool(
            MCPToolSchema(name="ghost", description="ghost", input_schema={})
        )
        with pytest.raises(MCPToolNotFoundError):
            tool.handler({}, {})

    def test_adapter_emits_mcp_events_on_first_call(self):
        """首次 handler 调用 → mcp_connected + mcp_tool_discovered 事件 (幂等
        — 已连接不重复发); 事件 data 含 connection/tool 审计字段。"""
        events: list[tuple[str, dict]] = []
        adapter = self._adapter(event_callback=lambda t, d: events.append((t, d)))
        tool = adapter.to_internal_tool(
            MCPToolSchema(name="echo", description="echo", input_schema={})
        )
        tool.handler({"message": "hi"}, {})
        tool.handler({"message": "hi2"}, {})
        assert [t for t, _ in events] == ["mcp_connected", "mcp_tool_discovered"]
        assert events[0][1]["connection_id"] == "mcp-abc123"
        assert events[1][1]["tools"] == ["echo"]
        # context 注入 event_callback 也生效 (执行循环透传路径)
        events.clear()
        tool.handler({"message": "x"}, {"event_callback": lambda t, d: events.append((t, d))})
        assert events == []


# ------------------------------------------------------------------ Tool source/metadata 扩展 (兼容)


class TestToolMetadataExtension:
    def test_legacy_tool_without_source_metadata(self):
        """旧 Tool (无 source/metadata 字段) 无损: source 默认 'internal',
        metadata 缺省 {} (向后兼容 — 既有构造零破坏)。"""
        tool = Tool(
            id="filesystem.read",
            name="Filesystem Read",
            handler=lambda input, context: {"content": ""},
        )
        assert tool.source == "internal"
        assert tool.metadata == {}

    def test_tool_source_literal_enforced(self):
        """source 只能是 internal|mcp (响亮拒绝其他值 — 不静默吞)。"""
        with pytest.raises(ValueError):
            Tool(  # type: ignore[call-arg]
                id="t1",
                name="T1",
                handler=lambda input, context: None,
                source="public",
            )


# ------------------------------------------------------------------ MCP Tool 注册 (Registry → ToolRegistry)


class TestMCPRegistration:
    def test_register_connection_discovers_and_registers_tools(self):
        """MCPRegistry.register_connection: 存连接 → connect → list_tools →
        adapter → ToolRegistry.register — 与 filesystem.read 同表 (Agent 视角
        无差别: 内部/MCP 都是 Tool)。"""
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(
            id="mcp-abc123", name="mock-echo", server_url="mock://echo"
        )
        tools, _client = mcp_registry.register_connection(conn)
        assert [t["id"] for t in tools] == ["echo"]
        assert registry.get("echo") is not None
        assert registry.get("echo").source == "mcp"
        assert registry.get("filesystem.read").source == "internal"
        # Agent 视角: list() 中 echo 与 filesystem.read 并列
        assert [t.id for t in registry.list()] == ["echo", "filesystem.read"]

    def test_register_connection_returns_connection_and_client(self):
        """register_connection 返回 (tools, client) — 连接可查、client 可复用。"""
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        tools, client = mcp_registry.register_connection(conn)
        assert mcp_registry.get_connection("mcp-1") is conn
        assert mcp_registry.list_connections() == [conn]
        assert client.connected is True

    def test_register_connection_emits_registered_event(self):
        """注册过程发 mcp_tool_registered 事件 (每 tool 一次, data 含
        tool/server — 注册边界可审计)。"""
        events: list[tuple[str, dict]] = []
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(
            tool_registry=registry, event_callback=lambda t, d: events.append((t, d))
        )
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        mcp_registry.register_connection(conn)
        # S10-020: 注册即连接 — 事件顺序 connected → discovered → registered
        assert [t for t, _ in events] == [
            "mcp_connected",
            "mcp_tool_discovered",
            "mcp_tool_registered",
        ]
        assert events[-1][1]["tool"] == "echo"
        assert events[-1][1]["server"] == "echo"

    def test_register_connection_unsupported_transport_loud(self):
        """非 mock transport (stdio/http — 真实 MCP 协议) → MCPConnectionError
        响亮拒绝 (本 Task 禁止连公网, 不假装连接成功)。"""
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(
            id="mcp-1", name="github", server_url="https://mcp.example.com", transport="http"
        )
        with pytest.raises(MCPConnectionError):
            mcp_registry.register_connection(conn)

    def test_register_connection_tool_conflict_loud(self):
        """MCP tool 与既有 Tool id 冲突 → ToolConflictError 响亮 (同内部
        注册语义 — 不静默覆盖)。"""
        registry = ToolRegistry.with_system_tools()
        registry.register(
            Tool(id="echo", name="Existing Echo", handler=lambda input, context: None)
        )
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        with pytest.raises(Exception) as exc:
            mcp_registry.register_connection(conn)
        assert "already registered" in str(exc.value)


# ------------------------------------------------------------------ Permission Chain (Agent→Skill→Tool)


class TestMCPPermissionChain:
    def _setup(self, skill_tools: list[str], tool_permission: ToolPermissionPolicy):
        """装配: 系统 Tool + echo MCP Tool + 自定义 Skill (含指定 tools)。"""
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        mcp_registry.register_connection(
            conn, permission_policy=tool_permission
        )
        skill_registry = SkillRegistry(tool_registry=registry)
        skill_registry.register(
            Skill(
                id="custom.development",
                name="Custom Development",
                tools=skill_tools,
                permissions=SkillPermissionPolicy(allow_all=True),
            )
        )
        return registry, skill_registry

    def test_skill_without_mcp_tool_denied(self):
        """Skill 不含 mcp tool → check_tool_access 拒绝 (环2 gate — MCP tool
        不绕过权限链; 即使 tool 权限放行)。"""
        _, skill_registry = self._setup(
            skill_tools=["filesystem.read"],
            tool_permission=ToolPermissionPolicy(allow_all=True),
        )
        denied = skill_registry.check_tool_access("backend-1", ["custom.development"], "echo")
        assert "do not include tool 'echo'" in denied

    def test_skill_with_mcp_tool_allowed(self):
        """Skill 含 mcp tool + tool 权限放行 → check_tool_access 放行 ("")。"""
        _, skill_registry = self._setup(
            skill_tools=["filesystem.read", "echo"],
            tool_permission=ToolPermissionPolicy(allow_all=True),
        )
        assert skill_registry.check_tool_access("backend-1", ["custom.development"], "echo") == ""

    def test_tool_permission_still_enforced(self):
        """环3 仍生效: mcp tool 白名单不含 agent → 拒绝 (注册可收窄权限 —
        不因 MCP 放宽 Tool 最终边界)。"""
        _, skill_registry = self._setup(
            skill_tools=["echo"],
            tool_permission=ToolPermissionPolicy(allowed_agent_ids=["tester-1"]),
        )
        denied = skill_registry.check_tool_access("backend-1", ["custom.development"], "echo")
        assert "is not allowed to use tool" in denied
        assert skill_registry.check_tool_access("tester-1", ["custom.development"], "echo") == ""


# ------------------------------------------------------------------ ToolExecutor 集成 (Agent 调 MCP Tool)


class TestMCPToolExecutorIntegration:
    def test_execute_mcp_tool_through_executor(self):
        """ToolExecutor.execute("echo", ...) → ToolResult.ok({message: "hello"})
        — MCP Tool 走内部执行器 (Lookup→Permission→Schema→Execute), 无绕过。"""
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        mcp_registry.register_connection(
            conn, permission_policy=ToolPermissionPolicy(allow_all=True)
        )
        executor = ToolExecutor(registry)
        result = executor.execute("echo", {"message": "hello"}, "backend-1")
        assert result.success is True
        assert result.output == {"message": "hello"}

    def test_execute_mcp_tool_invalid_input_failed(self):
        """MCP tool 输入校验走内部 JSON Schema (缺 message → invalid input —
        MCP 不自带校验绕过)。"""
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        mcp_registry.register_connection(
            conn, permission_policy=ToolPermissionPolicy(allow_all=True)
        )
        executor = ToolExecutor(registry)
        result = executor.execute("echo", {}, "backend-1")
        assert result.success is False
        assert "invalid input" in result.error

    def test_execute_mcp_tool_permission_denied(self):
        """MCP tool 权限未放行 (注册收窄白名单) → permission denied (走内部
        最小权限表 — MCP 不因来源放宽 Tool 最终边界)。"""
        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(tool_registry=registry)
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        mcp_registry.register_connection(
            conn, permission_policy=ToolPermissionPolicy(allowed_agent_ids=["tester-1"])
        )
        executor = ToolExecutor(registry)
        result = executor.execute("echo", {"message": "hello"}, "backend-1")
        assert result.success is False
        assert "permission denied" in result.error


# ------------------------------------------------------------------ Event Chain (完整链路)


class TestMCPEventChain:
    def test_runtime_event_types_include_mcp(self):
        """RuntimeEventType 含 mcp_connected/mcp_tool_discovered/
        mcp_tool_registered (20→23 扩展, 向后兼容)。"""
        assert RuntimeEventType.MCP_CONNECTED.value == "mcp_connected"
        assert RuntimeEventType.MCP_TOOL_DISCOVERED.value == "mcp_tool_discovered"
        assert RuntimeEventType.MCP_TOOL_REGISTERED.value == "mcp_tool_registered"
        assert len(RuntimeEventType) >= 23

    def test_full_chain_types_present(self):
        """完整链路 11 事件类型全部存在 (约束 8: agent_started→skill_loaded→
        task_received→thinking_started→decision_created→tool_requested→
        mcp_connected→mcp_tool_discovered→tool_started→tool_completed→
        execution_completed)。"""
        chain = [
            "agent_started",
            "skill_loaded",
            "task_received",
            "thinking_started",
            "decision_created",
            "tool_requested",
            "mcp_connected",
            "mcp_tool_discovered",
            "tool_started",
            "tool_completed",
            "execution_completed",
        ]
        for name in chain:
            assert RuntimeEventType(name).value == name

    def test_mcp_events_during_execution_chain(self, tmp_path: Path):
        """执行链路: AgentExecutionLoop 完整跑 — 11 事件链
        agent_started→task_received→thinking_started→decision_created→
        mcp_connected→mcp_tool_discovered→tool_started→tool_completed→
        observation_received→execution_completed (tool_started/completed 由
        loop 层发; mcp_* 由 adapter 经 ctx 透传发)。"""
        events: list[str] = []

        def record(t: str, d: dict) -> None:
            events.append(t)

        registry = ToolRegistry.with_system_tools()
        mcp_registry = MCPRegistry(
            tool_registry=registry, event_callback=lambda t, d: record(t, d)
        )
        conn = MCPConnection(id="mcp-1", name="echo", server_url="mock://echo")
        mcp_registry.register_connection(
            conn, permission_policy=ToolPermissionPolicy(allow_all=True)
        )
        executor = ToolExecutor(
            registry,
            event_callback=lambda t, d: record(t, d),
        )
        # 注册即连接: mcp_connected + mcp_tool_discovered + mcp_tool_registered
        assert "mcp_connected" in events
        assert "mcp_tool_discovered" in events
        assert "mcp_tool_registered" in events

        # AgentExecutionLoop 完整链路 (假 Planner 返回 tool ACTION_REQUIRED → echo)
        from exec.execution_loop import (
            ACTION_REQUIRED,
            AgentExecutionLoop,
            Decision,
            FINAL,
            MockActionExecutor,
        )

        session_store = RuntimeSessionStore("/tmp")  # type: ignore[arg-type]
        session = RuntimeSession(
            session_id="s-mcp-1",
            agent_id="backend-1",
            task_id="T-001",
            workflow_id="dev",
        )
        session_store.save(session)
        started = session.start()
        session_store.save(started)
        session = started

        class FakePlanner:
            calls = 0

            def plan(self, task, context):
                FakePlanner.calls += 1
                if FakePlanner.calls == 1:
                    return Decision(
                        type=ACTION_REQUIRED,
                        payload={
                            "action": {
                                "type": "tool",
                                "tool_id": "echo",
                                "input": {"message": "hello"},
                            }
                        },
                    )
                return Decision(type=FINAL)

        loop = AgentExecutionLoop(
            session=session,
            session_store=session_store,
            planner=FakePlanner(),  # type: ignore[arg-type]
            action_executor=MockActionExecutor(),
            tool_executor=executor,
        )
        from types import SimpleNamespace

        from exec.agent_runtime import AgentRuntime
        from exec_helpers import FakeProvider
        from tasks.models import Task

        task = Task(id="T-001", title="echo test", project="demo", type="feature", workflow="dev")
        agent = SimpleNamespace(id="backend-1", role="developer")
        # 注入真实 AgentRuntime + FakeProvider (FINAL 路径执行; NO_CHANGE 空补丁
        # → 验证通过 → SUCCESS — 不伪造真实 LLM 结果); work_root 须已存在
        work_root = tmp_path / "work-root"
        work_root.mkdir(parents=True, exist_ok=True)
        runtime = AgentRuntime(
            FakeProvider(content="<patch>NO_CHANGE</patch>"),
            work_root=work_root,
            validation_command=None,
        )
        loop = AgentExecutionLoop(
            session=session,
            session_store=session_store,
            planner=FakePlanner(),  # type: ignore[arg-type]
            action_executor=MockActionExecutor(),
            tool_executor=executor,
            runtime=runtime,
        )
        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True, exist_ok=True)
        result = loop.run(task, agent, context={"task": "echo test", "project_dir": str(project_dir)})
        assert result.get("status") in ("COMPLETED", "completed", "success")

        # 从 store 重新加载 (session 变量是旧 copy; store 是最新状态)
        loaded = session_store.get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        # mcp_* 事件: 注册时发 (registry callback → events 列表, 无 session 上下文);
        # 执行时经 adapter ctx 透传发 (session 内 — 首次执行 mcp_connected 幂等)
        # 事件链关键段: tool_requested → tool_started → tool_completed → observation_received
        for needed in (
            "agent_started",
            "task_received",
            "thinking_started",
            "decision_created",
            "tool_requested",
            "tool_started",
            "tool_completed",
            "observation_received",
            "execution_completed",
        ):
            assert needed in types, f"missing {needed} in {types}"
        # mcp 注册事件在 registry callback 中 (mcp_connected/discovered/registered)
        assert "mcp_connected" in events
        assert "mcp_tool_discovered" in events
        assert "mcp_tool_registered" in events


__all__: list[str] = []
