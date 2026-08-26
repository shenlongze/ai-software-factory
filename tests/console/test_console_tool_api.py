"""tests/console/test_console_tool_api.py — S10-018 Task 001c Tool API (Console) 测试。

覆盖 (Task 001c — Tool API + 前端收尾; 承接 Task 001b 截断点):
- api/__init__ 导出: list_tools/execute_tool 可调用 (test_route_modules_exported
  同源 — 本文件只做最小可调用断言)
- Service 层 (ConsoleService.list_tools/execute_tool + 注入 ToolExecutor):
  - list_tools: 注册表全量 → [{id, name, description, enabled}] (id 排序);
    未装配 → [] (失败安全 — GET 永不失败)
  - execute_tool 成功 (backend-1 读 workspace 内文件) → {success: true, output}
  - 空 tool_id/agent_id → ValueError (HTTP 400 — 工具标识/执行者必填)
  - Tool 不存在 → ToolExecuteNotFoundError (HTTP 404)
  - 权限拒绝 (其他 agent — 最小权限表) → ToolExecutePermissionError (HTTP 403)
  - 输入非法 (缺 required path) → ValueError (HTTP 400)
  - store/exec 未装配 (空构造) → None (404 失败安全)
- API 层 (真实装配 build_console_service → build_app → TestClient):
  - GET /api/tools → 200 {tools: [...]} filesystem.read 存在
  - POST /api/tools/filesystem.read/execute {agent_id: backend-1,
    input: {path: <workspace 内真实文件>}} → 200 {success: true, output}
  - 同工具其他 agent → 403 (最小权限表证明)
  - 不存在 tool → 404
  - 空 agent_id / 非法输入 (缺 path) → 400

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类跳过
(与 test_console_agent_executor_api.py / test_console_runtime_session_api.py 同模式)。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:
    sys.path.insert(0, str(_FACTORY_EXEC))

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_api = importlib.import_module("factory-console.api")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_service_mod = importlib.import_module("factory-console.service")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


def _system_executor(workspace_root: Path):
    """系统 Tool 装配 (with_system_tools → filesystem.read; backend-1 白名单)。"""
    from exec.tool import ToolExecutor, ToolRegistry

    return ToolExecutor(
        ToolRegistry.with_system_tools(),
        workspace_root=workspace_root,
    )


# ------------------------------------------------------------------ 路由导出


class TestToolRouteExports:
    def test_list_tools_and_execute_tool_exported(self):
        """api/ 暴露 Tool 路由函数 (list_tools/execute_tool — 11B 薄层绑定源)。"""
        assert callable(_api.list_tools)
        assert callable(_api.execute_tool)


# ------------------------------------------------------------------ Service 层


class TestToolService:
    def test_list_tools_returns_registry_tools(self, tmp_path: Path):
        """list_tools → [{id, name, description, enabled}] (id 排序;
        filesystem.read 在列)。"""
        executor = _system_executor(tmp_path / "ws")
        service = _service_mod.ConsoleService(tool_executor=executor)

        tools = service.list_tools()

        ids = [t["id"] for t in tools]
        # 服务层: 旧 ToolRegistry (filesystem.read); HTTP 层才合并统一注册表
        assert ids == ["filesystem.read"]
        tool = tools[0]
        assert tool["name"] == "Filesystem Read"
        assert tool["description"]
        assert tool["enabled"] is True

    def test_list_tools_unassembled_returns_empty(self, monkeypatch):
        """exec 未装配 (Removal Isolation — _tool_mod → None) → [] (失败安全 —
        GET 永不失败)。"""
        monkeypatch.setattr(
            _service_mod.ConsoleService, "_tool_mod", staticmethod(lambda: None)
        )
        service = _service_mod.ConsoleService()
        assert service.list_tools() == []

    def test_execute_tool_success_reads_workspace_file(self, tmp_path: Path):
        """execute_tool 成功: backend-1 读 workspace 内文件 → {success: true,
        output: {content, path}}。"""
        ws = tmp_path / "ws"
        ws.mkdir(parents=True)
        (ws / "notes.md").write_text("hello tool\n", encoding="utf-8")
        service = _service_mod.ConsoleService(tool_executor=_system_executor(ws))

        result = service.execute_tool(
            "filesystem.read", "backend-1", {"path": "notes.md"}
        )

        assert result["success"] is True
        assert result["output"]["content"] == "hello tool\n"
        assert result["output"]["path"] == "notes.md"

    def test_execute_tool_empty_ids_rejected(self):
        """空 tool_id/agent_id → ValueError (HTTP 400)。"""
        service = _service_mod.ConsoleService()
        with pytest.raises(ValueError, match="tool_id"):
            service.execute_tool("  ", "backend-1", {"path": "x"})
        with pytest.raises(ValueError, match="agent_id"):
            service.execute_tool("filesystem.read", "", {"path": "x"})

    def test_execute_tool_not_found(self, tmp_path: Path):
        """Tool 不存在 → ToolExecuteNotFoundError (HTTP 404)。"""
        ws = tmp_path / "ws"
        ws.mkdir(parents=True)
        service = _service_mod.ConsoleService(tool_executor=_system_executor(ws))
        with pytest.raises(_service_mod.ToolExecuteNotFoundError):
            service.execute_tool("nonexistent.tool", "backend-1", {})

    def test_execute_tool_permission_denied(self, tmp_path: Path):
        """其他 agent (非白名单) → ToolExecutePermissionError (HTTP 403 —
        最小权限表拒绝)。"""
        ws = tmp_path / "ws"
        ws.mkdir(parents=True)
        (ws / "notes.md").write_text("secret\n", encoding="utf-8")
        service = _service_mod.ConsoleService(tool_executor=_system_executor(ws))
        with pytest.raises(_service_mod.ToolExecutePermissionError):
            service.execute_tool(
                "filesystem.read", "flutter-dev", {"path": "notes.md"}
            )

    def test_execute_tool_invalid_input(self, tmp_path: Path):
        """输入非法 (缺 required path) → ValueError (HTTP 400)。"""
        ws = tmp_path / "ws"
        ws.mkdir(parents=True)
        service = _service_mod.ConsoleService(tool_executor=_system_executor(ws))
        with pytest.raises(ValueError, match="invalid input"):
            service.execute_tool("filesystem.read", "backend-1", {})

    def test_execute_tool_unassembled_returns_none(self, monkeypatch):
        """exec 未装配 (Removal Isolation — _tool_mod → None) → None (404 失败
        安全)。"""
        monkeypatch.setattr(
            _service_mod.ConsoleService, "_tool_mod", staticmethod(lambda: None)
        )
        service = _service_mod.ConsoleService()
        assert (
            service.execute_tool("filesystem.read", "backend-1", {"path": "x"})
            is None
        )


# ------------------------------------------------------------------ API 层


@requires_fastapi
def _api_client(factory_root: Path, *, event_logger=None):
    """真实装配 (build_console_service — 自装配系统 Tool; 失败安全)。"""
    service = _adapter.build_console_service(
        factory_root, event_logger=event_logger
    )
    app = _adapter.build_app(service, event_logger=event_logger)
    return TestClient(app)


@requires_fastapi
class TestToolApi:
    def test_list_tools_endpoint_contains_filesystem_read(self, tmp_path: Path):
        """GET /api/tools → 200 {tools: [...]} — filesystem.read 存在
        (自装配 ToolRegistry.with_system_tools)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.get("/api/tools")
            assert resp.status_code == 200, resp.text
            tools = resp.json()["tools"]
            ids = [t["id"] for t in tools]
        # U-1: /api/tools = 统一注册表 (39 内置) + 旧 ToolRegistry (filesystem.read 合并)
        assert "filesystem.read" in ids
        assert "code_exec" in ids and "monitor" in ids

    def test_execute_endpoint_success(self, tmp_path: Path):
        """POST /api/tools/filesystem.read/execute → 200 {success: true,
        output} — backend-1 读 workspace 内真实文件 (端到端真实 HTTP)。"""
        root = tmp_path / "factory"
        root.mkdir(parents=True, exist_ok=True)
        (root / "notes.md").write_text("hello tool\n", encoding="utf-8")
        with _api_client(root) as client:
            resp = client.post(
                "/api/tools/filesystem.read/execute",
                json={"agent_id": "backend-1", "input": {"path": "notes.md"}},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["success"] is True
            assert body["output"]["content"] == "hello tool\n"

    def test_execute_endpoint_permission_denied_403(self, tmp_path: Path):
        """同工具其他 agent → 403 (最小权限表 — 权限证明)。"""
        root = tmp_path / "factory"
        root.mkdir(parents=True, exist_ok=True)
        (root / "notes.md").write_text("secret\n", encoding="utf-8")
        with _api_client(root) as client:
            resp = client.post(
                "/api/tools/filesystem.read/execute",
                json={"agent_id": "flutter-dev", "input": {"path": "notes.md"}},
            )
            assert resp.status_code == 403, resp.text
            assert "permission denied" in resp.json()["error"]["message"]

    def test_execute_endpoint_tool_not_found_404(self, tmp_path: Path):
        """不存在 tool → 404。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.post(
                "/api/tools/nonexistent.tool/execute",
                json={"agent_id": "backend-1", "input": {}},
            )
            assert resp.status_code == 404, resp.text
            assert "tool not found" in resp.json()["error"]["message"]

    def test_execute_endpoint_empty_agent_400(self, tmp_path: Path):
        """空 agent_id → 400 (执行者必须明确)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.post(
                "/api/tools/filesystem.read/execute",
                json={"agent_id": "  ", "input": {"path": "notes.md"}},
            )
            assert resp.status_code == 400, resp.text

    def test_execute_endpoint_invalid_input_400(self, tmp_path: Path):
        """输入非法 (缺 required path) → 400 (schema 校验失败)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.post(
                "/api/tools/filesystem.read/execute",
                json={"agent_id": "backend-1", "input": {}},
            )
            assert resp.status_code == 400, resp.text
            assert "invalid input" in resp.json()["error"]["message"]
