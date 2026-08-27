"""MCP stdio client 单测 (S10-127 P2.3) — 假 server 验证协议全链路。

覆盖:
- initialize → tools/list → tools/call (echo_text)
- load_mcp_servers 从 mcp_servers.json 加载
- 工具调用结果文本解析
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MCP = _ROOT / "factory-console" / "session" / "mcp_client.py"

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


@pytest.fixture(scope="module")
def mcp():
    spec = importlib.util.spec_from_file_location("mcp_client", _MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_full_protocol_flow(mcp, tmp_path):
    server = tmp_path / "fake_server.py"
    server.write_text(FAKE_SERVER, encoding="utf-8")
    cfg = tmp_path / "mcp_servers.json"
    cfg.write_text(json.dumps({"servers": {"fake": {
        "command": sys.executable, "args": [str(server)]}}}), encoding="utf-8")

    clients = mcp.load_mcp_servers(str(tmp_path))
    assert "fake" in clients
    client = clients["fake"]
    tools = client.list_tools()
    names = [t["name"] for t in tools]
    assert "echo_text" in names

    r = client.call_tool("echo_text", {"text": "hi"})
    assert r["ok"] is True
    assert r["output"] == "echo: hi"
    client.stop()


def test_missing_config_empty(mcp, tmp_path):
    assert mcp.load_mcp_servers(str(tmp_path)) == {}
