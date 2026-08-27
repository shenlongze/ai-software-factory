"""MCP 工具接入会话工具面集成单测 (S10-127 P2.3)。

覆盖:
- mcp_tool_schemas: fake server 工具 → mcp__fake__echo_text schema
- dispatch mcp__fake__echo_text → echo 结果
- tool_schemas(data_dir): 含 MCP 工具 (不进首轮核心, 可被 tool_search 检索)
- 非法/未配置 MCP 工具 → 诚实错误
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

FAKE_SERVER = r'''import sys, json

def read_frame():
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            sys.exit(0)
        if line == "\r\n":
            break
        k, v = line.split(":", 1)
        headers[k.lower()] = int(v.strip())
    return json.loads(sys.stdin.read(headers["content-length"]))

def write_frame(obj):
    data = json.dumps(obj).encode()
    sys.stdout.write("Content-Length: " + str(len(data)) + "\r\n\r\n")
    sys.stdout.write(data.decode())
    sys.stdout.flush()

while True:
    msg = read_frame()
    m = msg.get("method")
    if m == "initialize":
        write_frame({"jsonrpc":"2.0","id":msg["id"],
                     "result":{"protocolVersion":"2025-03-26","capabilities":{},
                               "serverInfo":{"name":"fake","version":"1"}}})
    elif m == "tools/list":
        write_frame({"jsonrpc":"2.0","id":msg["id"],
                     "result":{"tools":[{"name":"echo_text",
                                         "description":"echo a message",
                                         "inputSchema":{"type":"object",
                                                       "properties":{"text":{"type":"string"}},
                                                       "required":["text"]}}]}})
    elif m == "tools/call":
        args = msg["params"].get("arguments") or {}
        write_frame({"jsonrpc":"2.0","id":msg["id"],
                     "result":{"content":[{"type":"text","text":"echo: " + str(args.get("text",""))}],
                               "isError":False}})
'''


@pytest.fixture
def mcp_dir(tmp_path):
    server = tmp_path / "fake_server.py"
    server.write_text(FAKE_SERVER, encoding="utf-8")
    (tmp_path / "mcp_servers.json").write_text(json.dumps({"servers": {"fake": {
        "command": sys.executable, "args": [str(server)]}}}), encoding="utf-8")
    return tmp_path


def test_mcp_tool_schemas(mcp_dir):
    from factory_console.session.mcp_tools import mcp_tool_schemas

    schemas = mcp_tool_schemas(str(mcp_dir))
    names = [str(s["function"]["name"]) for s in schemas]
    assert "mcp__fake__echo_text" in names
    s = next(x for x in schemas if x["function"]["name"] == "mcp__fake__echo_text")
    assert "MCP:fake" in s["function"]["description"]


def test_dispatch_mcp_call(mcp_dir):
    from factory_console.session.mcp_tools import dispatch_mcp

    r = dispatch_mcp("mcp__fake__echo_text", {"text": "hi"}, str(mcp_dir))
    assert r["ok"] is True
    assert r["output"] == "echo: hi"


def test_dispatch_mcp_unknown_server(mcp_dir):
    from factory_console.session.mcp_tools import dispatch_mcp

    r = dispatch_mcp("mcp__nope__tool", {}, str(mcp_dir))
    assert r["ok"] is False
    assert "未配置" in r["error"]


def test_dispatch_mcp_bad_name(mcp_dir):
    from factory_console.session.mcp_tools import dispatch_mcp

    r = dispatch_mcp("not_mcp", {}, str(mcp_dir))
    assert r["ok"] is False


def test_tool_schemas_contains_mcp(mcp_dir):
    from factory_console.session import agent_loop as _al

    tools = _al.tool_schemas(str(mcp_dir))
    names = [str((t.get("function") or {}).get("name")) for t in tools]
    assert "mcp__fake__echo_text" in names


def test_no_mcp_config_no_crash(tmp_path):
    from factory_console.session import agent_loop as _al
    from factory_console.session.mcp_tools import mcp_tool_schemas

    assert mcp_tool_schemas(str(tmp_path)) == []
    tools = _al.tool_schemas(str(tmp_path))
    assert not any(str((t.get("function") or {}).get("name") or "").startswith("mcp__") for t in tools)
