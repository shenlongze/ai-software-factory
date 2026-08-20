"""tests/exec/test_exec_mcp_stdio.py — StdioMCPClient (M1 真 MCP 连接, 增强层)。

覆盖: 拉起子进程 JSON-RPC stdio (initialize/initialized/tools/list/tools/call),
列表/调用往返, 断开, 连接失败响亮报错。fake server 用本机 python 子进程
(行分隔 JSON), 不连公网。
basename 全仓库唯一 (test_exec_* 前缀)。
"""

from __future__ import annotations

import sys

import pytest

from exec.mcp import (
    MCPConnectionError,
    StdioMCPClient,
)

_FAKE_SERVER = r'''
import json, sys

def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue
    method = msg.get("method")
    rid = msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "serverInfo": {"name": "fake", "version": "1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": "greet", "description": "say hi",
             "inputSchema": {"type": "object",
                             "properties": {"name": {"type": "string"}}}}]}})
    elif method == "tools/call":
        args = (msg.get("params") or {}).get("arguments") or {}
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": "hi " + str(args.get("name", ""))}],
            "isError": False}})
'''


def _client() -> StdioMCPClient:
    return StdioMCPClient(sys.executable, ["-c", _FAKE_SERVER], name="fake")


class TestStdioMCPClient:
    def test_connect_initialize_and_state(self):
        c = _client()
        assert not c.connected
        c.connect()
        assert c.connected
        c.disconnect()
        assert not c.connected

    def test_list_tools_returns_schema(self):
        c = _client()
        c.connect()
        try:
            tools = c.list_tools()
            assert [t.name for t in tools] == ["greet"]
            assert tools[0].description == "say hi"
            assert tools[0].input_schema.get("type") == "object"
        finally:
            c.disconnect()

    def test_call_tool_roundtrip(self):
        c = _client()
        c.connect()
        try:
            result = c.call_tool("greet", {"name": "alice"})
            assert result["content"] == ["hi alice"]
            assert result["isError"] is False
        finally:
            c.disconnect()

    def test_connect_missing_command_loud(self):
        c = StdioMCPClient("/no/such/binary", [], name="nope")
        with pytest.raises(MCPConnectionError):
            c.connect()

    def test_disconnect_idempotent(self):
        c = _client()
        c.disconnect()
        assert not c.connected

    def test_call_before_connect_loud(self):
        c = _client()
        with pytest.raises(MCPConnectionError):
            c.list_tools()
