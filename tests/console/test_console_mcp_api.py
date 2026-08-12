"""tests/console/test_console_mcp_api.py — S10-020 Task 001c MCP API (Console) 测试。

覆盖 (Task 001c — MCP Console/API/前端收尾; 承接 Task 001b 断点):
- api/__init__ 导出: list_mcp_connections/create_mcp_connection/list_mcp_tools
  可调用 (test_route_modules_exported 同源 — 本文件只做最小可调用断言)
- Service 层 (ConsoleService.mcp_connections/create_mcp_connection/mcp_tools +
  注入 MCPRegistry/ToolExecutor):
  - mcp_connections: 注册后 → [{id, name, server_url, transport, enabled,
    created_at}] (id 排序); 未装配 → [] (失败安全 — GET 永不失败)
  - create_mcp_connection 成功 (mock transport — 注册即连接 + Tool 注册) →
    {id, name, server_url, transport, enabled, tools: [{id: "echo", ...}]}
  - 空 name/server_url → ValueError (HTTP 400 — 连接标识/地址必填)
  - stdio/http 真实协议 → ValueError (HTTP 400 — MCPConnectionError 归一,
    响亮拒绝不假装连接成功)
  - store/exec 未装配 (空构造) → None (404 失败安全)
  - mcp_tools: 注册 MCP 连接后 → [{id: "echo", ...}] (source=mcp 过滤);
    未装配 → [] (失败安全)
- API 层 (真实装配 build_console_service → build_app → TestClient):
  - GET /api/mcp/connections → 200 {connections: [...]} (空 → [])
  - POST /api/mcp/connections {name, server_url, transport: "mock"} → 200
    {id: mcp-*, tools: [{id: "echo"}]}
  - 空 name → 400; stdio transport → 400 (响亮拒绝)
  - GET /api/mcp/tools → 200 {tools: [...]} echo 在列 (source=mcp)
  - 注册后 GET /api/mcp/connections → 连接列表含刚注册连接

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类跳过
(与 test_console_tool_api.py / test_console_runtime_session_api.py 同模式)。
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


def _mcp_assembled(tmp_path: Path, *, with_tool_registry: bool = True):
    """MCP 装配: ToolExecutor (系统 Tool) + MCPRegistry (关联注册表)。"""
    from exec.mcp import MCPRegistry
    from exec.tool import ToolExecutor, ToolRegistry

    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    executor = ToolExecutor(ToolRegistry.with_system_tools(), workspace_root=ws)
    if with_tool_registry:
        registry = MCPRegistry(tool_registry=executor.registry)
    else:
        registry = MCPRegistry(tool_registry=None)
    return registry, executor


# ------------------------------------------------------------------ 路由导出


class TestMCPRouteExports:
    def test_mcp_route_functions_exported(self):
        """api/ 暴露 MCP 路由函数 (list_mcp_connections/create_mcp_connection/
        list_mcp_tools — 11B 薄层绑定源)。"""
        assert callable(_api.list_mcp_connections)
        assert callable(_api.create_mcp_connection)
        assert callable(_api.list_mcp_tools)


# ------------------------------------------------------------------ Service 层


class TestMCPService:
    def test_mcp_connections_unassembled_returns_empty(self, monkeypatch):
        """exec 未装配 (Removal Isolation — _mcp_mod → None) → [] (失败安全 —
        GET 永不失败)。"""
        monkeypatch.setattr(
            _service_mod.ConsoleService, "_mcp_mod", staticmethod(lambda: None)
        )
        service = _service_mod.ConsoleService()
        assert service.mcp_connections() == []

    def test_mcp_tools_unassembled_returns_empty(self, monkeypatch):
        """exec 未装配 → [] (失败安全 — GET 永不失败)。"""
        monkeypatch.setattr(
            _service_mod.ConsoleService, "_mcp_mod", staticmethod(lambda: None)
        )
        service = _service_mod.ConsoleService()
        assert service.mcp_tools() == []

    def test_create_mcp_connection_unassembled_returns_none(self, monkeypatch):
        """exec 未装配 → None (404 失败安全 — 写路径诚实失败)。"""
        monkeypatch.setattr(
            _service_mod.ConsoleService, "_mcp_mod", staticmethod(lambda: None)
        )
        service = _service_mod.ConsoleService()
        assert service.create_mcp_connection("demo", "mock://demo") is None

    def test_create_mcp_connection_empty_name_rejected(self, tmp_path: Path):
        """空 name → ValueError (HTTP 400 — 连接名称必填)。"""
        registry, executor = _mcp_assembled(tmp_path)
        service = _service_mod.ConsoleService(
            mcp_registry=registry, tool_executor=executor
        )
        with pytest.raises(ValueError, match="name"):
            service.create_mcp_connection("  ", "mock://demo")

    def test_create_mcp_connection_empty_url_rejected(self, tmp_path: Path):
        """空 server_url → ValueError (HTTP 400 — 服务地址必填)。"""
        registry, executor = _mcp_assembled(tmp_path)
        service = _service_mod.ConsoleService(
            mcp_registry=registry, tool_executor=executor
        )
        with pytest.raises(ValueError, match="server_url"):
            service.create_mcp_connection("demo", "  ")

    def test_create_mcp_connection_stdio_rejected(self, tmp_path: Path):
        """stdio 真实协议 → ValueError (HTTP 400 — MCPConnectionError 归一;
        本 Task 仅 mock 可用, 响亮拒绝不假装连接成功)。"""
        registry, executor = _mcp_assembled(tmp_path)
        service = _service_mod.ConsoleService(
            mcp_registry=registry, tool_executor=executor
        )
        with pytest.raises(ValueError, match="unsupported MCP transport"):
            service.create_mcp_connection("demo", "stdio://x", transport="stdio")

    def test_create_mcp_connection_success_registers_echo(self, tmp_path: Path):
        """mock 连接注册成功 (注册即连接 + Tool 注册) → 摘要含 echo。"""
        registry, executor = _mcp_assembled(tmp_path)
        service = _service_mod.ConsoleService(
            mcp_registry=registry, tool_executor=executor
        )

        result = service.create_mcp_connection("demo-mcp", "mock://demo")

        assert result["id"].startswith("mcp-")
        assert result["name"] == "demo-mcp"
        assert result["server_url"] == "mock://demo"
        assert result["transport"] == "mock"
        assert result["enabled"] is True
        assert [t["id"] for t in result["tools"]] == ["echo"]

    def test_mcp_connections_lists_registered(self, tmp_path: Path):
        """注册后 mcp_connections → 连接列表 (id 排序; 含新建连接)。"""
        registry, executor = _mcp_assembled(tmp_path)
        service = _service_mod.ConsoleService(
            mcp_registry=registry, tool_executor=executor
        )
        created = service.create_mcp_connection("demo-mcp", "mock://demo")

        connections = service.mcp_connections()

        assert len(connections) == 1
        conn = connections[0]
        assert conn["id"] == created["id"]
        assert conn["name"] == "demo-mcp"
        assert conn["server_url"] == "mock://demo"
        assert conn["transport"] == "mock"
        assert conn["enabled"] is True
        assert conn["created_at"]

    def test_mcp_tools_lists_echo_only(self, tmp_path: Path):
        """注册 MCP 连接后 mcp_tools → [echo] (source=mcp 过滤 — 内部
        filesystem.read 不在列)。"""
        registry, executor = _mcp_assembled(tmp_path)
        service = _service_mod.ConsoleService(
            mcp_registry=registry, tool_executor=executor
        )
        service.create_mcp_connection("demo-mcp", "mock://demo")

        tools = service.mcp_tools()

        assert [t["id"] for t in tools] == ["echo"]
        tool = tools[0]
        assert tool["name"] == "echo"
        assert tool["description"]
        assert tool["server"] == "demo-mcp"

    def test_mcp_tools_empty_before_connection(self, tmp_path: Path):
        """未注册任何 MCP 连接 → mcp_tools == [] (内部 tool 不混入)。"""
        registry, executor = _mcp_assembled(tmp_path)
        service = _service_mod.ConsoleService(
            mcp_registry=registry, tool_executor=executor
        )
        assert service.mcp_tools() == []

    def test_create_mcp_connection_without_tool_registry(self, tmp_path: Path):
        """MCPRegistry 无关联 ToolRegistry (仅连接管理) → 注册仍成功,
        tools 摘要来自发现 (不落内部注册表)。"""
        registry, _executor = _mcp_assembled(tmp_path, with_tool_registry=False)
        service = _service_mod.ConsoleService(mcp_registry=registry)

        result = service.create_mcp_connection("demo-mcp", "mock://demo")

        assert result["id"].startswith("mcp-")
        assert [t["id"] for t in result["tools"]] == ["echo"]
        assert service.mcp_tools() == []


# ------------------------------------------------------------------ API 层


@requires_fastapi
def _api_client(factory_root: Path, *, event_logger=None):
    """真实装配 (build_console_service — 自装配 MCPRegistry + 系统 Tool)。"""
    service = _adapter.build_console_service(
        factory_root, event_logger=event_logger
    )
    app = _adapter.build_app(service, event_logger=event_logger)
    return TestClient(app)


@requires_fastapi
class TestMCPApi:
    def test_list_connections_endpoint_empty(self, tmp_path: Path):
        """GET /api/mcp/connections → 200 {connections: []} (未注册 — 失败安全)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.get("/api/mcp/connections")
            assert resp.status_code == 200, resp.text
            assert resp.json() == {"connections": []}

    def test_create_connection_endpoint_registers_echo(self, tmp_path: Path):
        """POST /api/mcp/connections {name, server_url, transport: mock} →
        200 {id: mcp-*, tools: [echo]} (注册即连接 — Mock 不连公网)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.post(
                "/api/mcp/connections",
                json={"name": "demo-mcp", "server_url": "mock://demo", "transport": "mock"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["id"].startswith("mcp-")
            assert body["name"] == "demo-mcp"
            assert body["transport"] == "mock"
            assert [t["id"] for t in body["tools"]] == ["echo"]

    def test_create_connection_empty_name_400(self, tmp_path: Path):
        """POST 空 name → 400 (Service 层 ValueError 映射)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.post(
                "/api/mcp/connections",
                json={"name": "  ", "server_url": "mock://demo"},
            )
            assert resp.status_code == 400, resp.text
            assert "name" in resp.json()["detail"]

    def test_create_connection_stdio_400(self, tmp_path: Path):
        """POST stdio 真实协议 → 400 (响亮拒绝 — 本 Task 仅 mock 可用)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            resp = client.post(
                "/api/mcp/connections",
                json={"name": "demo-mcp", "server_url": "stdio://x", "transport": "stdio"},
            )
            assert resp.status_code == 400, resp.text
            assert "unsupported MCP transport" in resp.json()["detail"]

    def test_list_tools_endpoint_contains_echo(self, tmp_path: Path):
        """GET /api/mcp/tools → 200 {tools: [...]} — 注册后 echo 在列
        (source=mcp 过滤; filesystem.read 不在列)。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            client.post(
                "/api/mcp/connections",
                json={"name": "demo-mcp", "server_url": "mock://demo", "transport": "mock"},
            )
            resp = client.get("/api/mcp/tools")
            assert resp.status_code == 200, resp.text
            tools = resp.json()["tools"]
            assert [t["id"] for t in tools] == ["echo"]
            assert tools[0]["server"] == "demo-mcp"

    def test_list_connections_endpoint_after_create(self, tmp_path: Path):
        """注册后 GET /api/mcp/connections → 连接列表含新建连接。"""
        root = tmp_path / "factory"
        with _api_client(root) as client:
            created = client.post(
                "/api/mcp/connections",
                json={"name": "demo-mcp", "server_url": "mock://demo", "transport": "mock"},
            ).json()
            resp = client.get("/api/mcp/connections")
            assert resp.status_code == 200, resp.text
            connections = resp.json()["connections"]
            assert [c["id"] for c in connections] == [created["id"]]
            assert connections[0]["name"] == "demo-mcp"
