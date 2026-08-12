"""tests/exec/test_exec_tool.py — S10-018 Task 001 Tool Runtime Foundation 测试。

覆盖 (Tool Domain / ToolResult / PermissionPolicy / ToolRegistry / ToolExecutor /
filesystem sandbox — 纯内部 Tool Runtime, 不绑 OpenAI/MCP):
- Tool 模型: id/name/description/input_schema/output_schema/handler/
  permission_policy/enabled/created_at 字段完整; handler 可调用; 默认 enabled
- ToolResult: {success, output, error, metadata}; ok/failed 工厂 (失败带明确 error)
- PermissionPolicy: allowed_agent_ids 白名单 / allow_all / 默认禁止 (最小权限)
- ToolRegistry: register (id 冲突 → 明确错误) / unregister (不存在 → 明确错误) /
  get / list (排序) / validate (schema+handler 校验) / with_system_tools
  (启动加载系统 Tool: filesystem.read)
- ToolExecutor: Lookup → Permission → Schema Validation → Execute → ToolResult;
  失败明确不吞 (tool not found / disabled / permission denied / invalid input /
  handler error 全部 → ToolResult.failed + 明确 error)
- filesystem.read 沙箱: workspace 内正常读 / 路径穿越 (../) 阻止 / 绝对路径拒绝 /
  symlink 逃逸阻止 / 不存在 / 目录 / 空路径 — 禁任意系统路径

basename 全仓库唯一 (test_exec_* 前缀); 依赖 tests/exec/conftest.py 的 sys.path
(factory-exec 挂载, `exec` 包导入)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.tool import (
    Tool,
    ToolConflictError,
    ToolNotFoundError,
    ToolPermissionPolicy,
    ToolRegistry,
    ToolResult,
    ToolValidationError,
)


# ------------------------------------------------------------------ Tool 模型


class TestToolModel:
    def test_tool_model_fields_complete(self):
        """Tool 字段完整: id/name/description/input_schema/output_schema/handler/
        permission_policy/enabled/created_at (纯内部模型, 无 OpenAI/MCP 绑定)。"""
        tool = Tool(
            id="filesystem.read",
            name="Filesystem Read",
            description="读取 workspace 内文件",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            output_schema={"type": "object"},
            handler=lambda input, context: {"content": ""},
        )
        assert tool.id == "filesystem.read"
        assert tool.name == "Filesystem Read"
        assert tool.description == "读取 workspace 内文件"
        assert tool.input_schema["properties"]["path"]["type"] == "string"
        assert tool.output_schema["type"] == "object"
        assert callable(tool.handler)
        assert tool.enabled is True
        assert tool.created_at is not None

    def test_tool_defaults(self):
        """缺省字段: description 空串 / permission_policy 默认 (默认禁止) /
        enabled=True / created_at 自动。"""
        tool = Tool(id="t1", name="T1", handler=lambda input, context: None)
        assert tool.description == ""
        assert tool.enabled is True
        assert tool.permission_policy.allowed_agent_ids == []
        assert tool.permission_policy.allow_all is False
        assert tool.created_at is not None


class TestToolResult:
    def test_tool_result_success(self):
        """ToolResult 成功: {success: true, output, error 空, metadata 缺省 {}}。"""
        result = ToolResult(success=True, output={"content": "hello"})
        assert result.success is True
        assert result.output == {"content": "hello"}
        assert result.error == ""
        assert result.metadata == {}

    def test_tool_result_ok_factory(self):
        """ToolResult.ok 工厂: output + 可选 metadata。"""
        result = ToolResult.ok(output={"content": "x"}, metadata={"tool_id": "t1"})
        assert result.success is True
        assert result.output == {"content": "x"}
        assert result.metadata == {"tool_id": "t1"}

    def test_tool_result_failed_factory(self):
        """ToolResult.failed 工厂: success=false + 明确 error (失败不吞)。"""
        result = ToolResult.failed("permission denied")
        assert result.success is False
        assert result.output is None
        assert result.error == "permission denied"

    def test_tool_result_error_required_on_failure(self):
        """失败结果必须有 error (空 error 的失败 → 校验拒绝, 禁止静默)。"""
        with pytest.raises(Exception):
            ToolResult(success=False, error="")


# ------------------------------------------------------------------ PermissionPolicy


class TestToolPermissionPolicy:
    def test_default_denies_everyone(self):
        """默认策略 (空白名单 + allow_all=False) → 全部拒绝 (最小权限)。"""
        policy = ToolPermissionPolicy()
        assert policy.allows("backend-1") is False
        assert policy.allows("any-agent") is False

    def test_allowed_agent_ids_allowlist(self):
        """allowed_agent_ids 白名单: 命中放行, 其他拒绝。"""
        policy = ToolPermissionPolicy(allowed_agent_ids=["backend-1"])
        assert policy.allows("backend-1") is True
        assert policy.allows("flutter-dev") is False
        assert policy.allows("tester-1") is False

    def test_allow_all(self):
        """allow_all=True → 任意 agent 放行 (未来内部工具显式开放)。"""
        policy = ToolPermissionPolicy(allow_all=True)
        assert policy.allows("anything") is True


# ------------------------------------------------------------------ ToolRegistry


def _make_tool(tool_id: str = "filesystem.read", **kw) -> Tool:
    defaults = dict(
        name="Filesystem Read",
        description="读取 workspace 内文件",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=lambda input, context: {"content": ""},
        permission_policy=ToolPermissionPolicy(allowed_agent_ids=["backend-1"]),
    )
    defaults.update(kw)
    return Tool(id=tool_id, **defaults)


class TestToolRegistry:
    def test_register_and_get(self):
        """register → get 返回同一 Tool (按 id)。"""
        registry = ToolRegistry()
        tool = _make_tool()
        registry.register(tool)
        assert registry.get("filesystem.read") is tool

    def test_register_id_conflict_error(self):
        """register 同 id 二次 → ToolConflictError (响亮, 不静默覆盖)。"""
        registry = ToolRegistry()
        registry.register(_make_tool())
        with pytest.raises(ToolConflictError, match="filesystem.read"):
            registry.register(_make_tool())

    def test_get_missing_returns_none(self):
        """get 不存在 id → None (查询语义, 非错误)。"""
        registry = ToolRegistry()
        assert registry.get("nope") is None

    def test_unregister(self):
        """unregister → get None; 其余 Tool 不受影响。"""
        registry = ToolRegistry()
        registry.register(_make_tool())
        registry.register(_make_tool("other.tool"))
        registry.unregister("filesystem.read")
        assert registry.get("filesystem.read") is None
        assert registry.get("other.tool") is not None

    def test_unregister_missing_error(self):
        """unregister 不存在 id → ToolNotFoundError (响亮, 不静默)。"""
        registry = ToolRegistry()
        with pytest.raises(ToolNotFoundError, match="nope"):
            registry.unregister("nope")

    def test_list_sorted_by_id(self):
        """list 全部 Tool, 按 id 排序 (审计友好)。"""
        registry = ToolRegistry()
        registry.register(_make_tool("z.tool"))
        registry.register(_make_tool("a.tool"))
        assert [t.id for t in registry.list()] == ["a.tool", "z.tool"]

    def test_validate_rejects_empty_id(self):
        """validate: 空 id → ToolValidationError (响亮)。"""
        with pytest.raises(ToolValidationError):
            ToolRegistry.validate(Tool(id="", name="T", handler=lambda i, c: None))

    def test_validate_rejects_missing_handler(self):
        """validate: handler 非可调用 → ToolValidationError (响亮, 注册前拒绝)。"""
        tool = Tool.model_construct(id="t1", name="T", handler=None)  # 绕过构造校验
        with pytest.raises(ToolValidationError):
            ToolRegistry.validate(tool)

    def test_validate_rejects_non_dict_schema(self):
        """validate: input_schema/output_schema 非 dict → ToolValidationError。"""
        tool = Tool.model_construct(
            id="t1", name="T", handler=lambda i, c: None, input_schema=[]  # type: ignore[arg-type]
        )
        with pytest.raises(ToolValidationError):
            ToolRegistry.validate(tool)

    def test_with_system_tools_loads_filesystem_read(self):
        """with_system_tools: 启动加载系统 Tool — filesystem.read 存在且合法。"""
        registry = ToolRegistry.with_system_tools()
        tool = registry.get("filesystem.read")
        assert tool is not None
        assert tool.name
        assert tool.description
        assert callable(tool.handler)
        assert tool.input_schema.get("type") == "object"


# ------------------------------------------------------------------ ToolExecutor


def _make_executor(
    registry: ToolRegistry | None = None,
    *,
    workspace_root: Path | None = None,
    tool: Tool | None = None,
) -> tuple[ToolExecutor, ToolRegistry, Path]:
    """最小 ToolExecutor 装配: 可选注入 Tool / workspace 沙箱根 (tmp 目录)。"""
    from exec.tool import ToolExecutor

    ws = workspace_root or Path("/tmp/__tool_ws_placeholder__")
    reg = registry or ToolRegistry()
    if tool is not None:
        reg.register(tool)
    return ToolExecutor(reg, workspace_root=ws), reg, ws


def _echo_tool() -> Tool:
    """回显 Tool (handler 直接返回 input — 验证 Lookup→Permission→Schema→Execute)。"""
    return Tool(
        id="echo.tool",
        name="Echo",
        description="回显输入",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}, "count": {"type": "integer"}},
            "required": ["text"],
        },
        output_schema={"type": "object"},
        handler=lambda input, context: {"echo": input.get("text"), "agent": context.get("agent_id")},
        permission_policy=ToolPermissionPolicy(allowed_agent_ids=["backend-1"]),
    )


def _boom_tool() -> Tool:
    """抛异常的 Tool (handler error → 明确失败, 不吞)。"""

    def _boom(input, context):
        raise RuntimeError("boom: handler failure")

    return Tool(
        id="boom.tool",
        name="Boom",
        handler=_boom,
        permission_policy=ToolPermissionPolicy(allowed_agent_ids=["backend-1"]),
    )


class TestToolExecutor:
    def test_execute_success(self):
        """正常执行: 白名单 agent → Schema 通过 → handler → ToolResult.ok。"""
        executor, _reg, _ws = _make_executor(tool=_echo_tool())
        result = executor.execute("echo.tool", {"text": "hi"}, "backend-1")
        assert result.success is True
        assert result.output == {"echo": "hi", "agent": "backend-1"}
        assert result.error == ""

    def test_execute_tool_not_found(self):
        """Lookup 失败: 未注册 id → ToolResult.failed + 明确 error (不抛)。"""
        executor, _reg, _ws = _make_executor(tool=_echo_tool())
        result = executor.execute("nope.tool", {}, "backend-1")
        assert result.success is False
        assert "nope.tool" in result.error

    def test_execute_disabled_tool(self):
        """Enabled 检查: disabled Tool → ToolResult.failed (明确拒绝)。"""
        tool = _echo_tool().model_copy(update={"enabled": False})
        executor, _reg, _ws = _make_executor(tool=tool)
        result = executor.execute("echo.tool", {"text": "hi"}, "backend-1")
        assert result.success is False
        assert "disabled" in result.error

    def test_execute_permission_denied(self):
        """权限失败: 非白名单 agent → ToolResult.failed + 'permission denied'。"""
        executor, _reg, _ws = _make_executor(tool=_echo_tool())
        for agent_id in ("flutter-dev", "tester-1", "unknown-agent"):
            result = executor.execute("echo.tool", {"text": "hi"}, agent_id)
            assert result.success is False
            assert "permission denied" in result.error
            assert agent_id in result.error

    def test_execute_schema_invalid(self):
        """Schema 校验失败: 缺 required / 类型不符 → ToolResult.failed + 明确信息。"""
        executor, _reg, _ws = _make_executor(tool=_echo_tool())
        missing = executor.execute("echo.tool", {}, "backend-1")
        assert missing.success is False
        assert "missing required field" in missing.error
        wrong_type = executor.execute("echo.tool", {"text": 123}, "backend-1")
        assert wrong_type.success is False
        assert "must be string" in wrong_type.error

    def test_execute_handler_error_not_swallowed(self):
        """handler 异常 → ToolResult.failed + 'handler error: ...' (不吞异常, 不抛)。"""
        executor, _reg, _ws = _make_executor(tool=_boom_tool())
        result = executor.execute("boom.tool", {}, "backend-1")
        assert result.success is False
        assert "handler error" in result.error
        assert "boom" in result.error

    def test_execute_empty_agent_denied(self):
        """空 agent_id → 权限失败 (默认禁止 — 最小权限)。"""
        executor, _reg, _ws = _make_executor(tool=_echo_tool())
        result = executor.execute("echo.tool", {"text": "hi"}, "")
        assert result.success is False
        assert "permission denied" in result.error


# ------------------------------------------------------------------ filesystem.read 沙箱


def _fs_executor(tmp_path: Path) -> tuple[ToolExecutor, Path]:
    """真实 filesystem.read 装配: workspace 沙箱根 = tmp_path/workspace。"""
    from exec.tool import ToolRegistry, ToolExecutor

    ws = tmp_path / "workspace"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "parser.py").write_text("# parser\n", encoding="utf-8")
    (ws / "README.md").write_text("# demo\n", encoding="utf-8")
    registry = ToolRegistry.with_system_tools()
    return ToolExecutor(registry, workspace_root=ws), ws


class TestFilesystemReadTool:
    def test_read_workspace_file_ok(self, tmp_path: Path):
        """沙箱内正常读: {path: "src/parser.py"} → 文件内容。"""
        executor, _ws = _fs_executor(tmp_path)
        result = executor.execute("filesystem.read", {"path": "src/parser.py"}, "backend-1")
        assert result.success is True
        assert result.output["content"] == "# parser\n"
        assert result.output["path"] == "src/parser.py"

    def test_read_nested_relative_ok(self, tmp_path: Path):
        """嵌套相对路径正常读 (workspace 内任意深度)。"""
        executor, ws = _fs_executor(tmp_path)
        (ws / "a" / "b").mkdir(parents=True)
        (ws / "a" / "b" / "deep.txt").write_text("deep\n", encoding="utf-8")
        result = executor.execute("filesystem.read", {"path": "a/b/deep.txt"}, "backend-1")
        assert result.success is True
        assert result.output["content"] == "deep\n"

    def test_read_traversal_blocked(self, tmp_path: Path):
        """路径穿越 (../) → ToolResult.failed 'outside workspace' (防穿越)。"""
        executor, _ws = _fs_executor(tmp_path)
        secret = tmp_path / "secret.txt"
        secret.write_text("secret\n", encoding="utf-8")
        for evil in ("../secret.txt", "src/../../secret.txt", "..%2Fsecret.txt"):
            result = executor.execute("filesystem.read", {"path": evil}, "backend-1")
            assert result.success is False, evil
            assert (
                "outside workspace" in result.error
                or "encoded separators" in result.error
            ), evil

    def test_read_absolute_path_blocked(self, tmp_path: Path):
        """绝对路径 → 拒绝 (禁任意系统路径: /etc/passwd, 盘符, ~)。"""
        executor, _ws = _fs_executor(tmp_path)
        for evil in ("/etc/passwd", "/Users/me/secret.txt", "C:\\Windows\\x", "~/secret"):
            result = executor.execute("filesystem.read", {"path": evil}, "backend-1")
            assert result.success is False, evil
            assert (
                "outside workspace" in result.error
                or "must be relative" in result.error
            ), evil

    def test_read_symlink_escape_blocked(self, tmp_path: Path):
        """symlink 逃逸: workspace 内链接指向外部 → resolve 后拒绝 (防穿越)。"""
        executor, ws = _fs_executor(tmp_path)
        secret = tmp_path / "secret.txt"
        secret.write_text("secret\n", encoding="utf-8")
        (ws / "link.txt").symlink_to(secret)
        result = executor.execute("filesystem.read", {"path": "link.txt"}, "backend-1")
        assert result.success is False
        assert "outside workspace" in result.error

    def test_read_missing_file(self, tmp_path: Path):
        """文件不存在 → ToolResult.failed + 明确 error。"""
        executor, _ws = _fs_executor(tmp_path)
        result = executor.execute("filesystem.read", {"path": "nope.txt"}, "backend-1")
        assert result.success is False
        assert "nope.txt" in result.error

    def test_read_directory_rejected(self, tmp_path: Path):
        """目录路径 → ToolResult.failed (只读文件, 不递归)。"""
        executor, _ws = _fs_executor(tmp_path)
        result = executor.execute("filesystem.read", {"path": "src"}, "backend-1")
        assert result.success is False

    def test_read_empty_path_rejected(self, tmp_path: Path):
        """空 path / 缺失 → Schema 校验失败 (required 拒绝)。"""
        executor, _ws = _fs_executor(tmp_path)
        for evil in ({}, {"path": ""}, {"path": "   "}):
            result = executor.execute("filesystem.read", evil, "backend-1")
            assert result.success is False, evil

    def test_read_permission_denied(self, tmp_path: Path):
        """backend-1 允许 filesystem.read; 其他 Agent 默认禁止 (约束 8/9)。"""
        executor, _ws = _fs_executor(tmp_path)
        ok = executor.execute("filesystem.read", {"path": "README.md"}, "backend-1")
        assert ok.success is True
        denied = executor.execute("filesystem.read", {"path": "README.md"}, "flutter-dev")
        assert denied.success is False
        assert "permission denied" in denied.error


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
