"""factory-console/session/mcp_client.py — MCP stdio client 最小实现 (S10-127 P2.3).

MCP (Model Context Protocol): 外部工具统一协议接入 (三方标准)。
零依赖 stdio 客户端 (JSON-RPC 2.0 over stdio, Content-Length 帧):
- initialize → notifications/initialized → tools/list → tools/call
支持: 多 server (mcp_servers.json: {name: {command, args}}); 工具名 mcp__<server>__<tool>。
失败安全: server 启动/请求失败 → 该 server 工具不可用, 不拖垮会话。
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import uuid
from typing import Any

logger = logging.getLogger("factory.mcp")

_PROTOCOL_VERSION = "2025-03-26"
_READ_TIMEOUT = 60


class McpError(Exception):
    """MCP 基础错误。"""


class McpClient:
    """单个 MCP stdio server 的客户端。"""

    def __init__(self, name: str, command: str, args: list[str] | None = None):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._buffer = b""
        self._ready = False

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._ready:
            return
        try:
            self._proc = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=False,
            )
            init = self._request("initialize", {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ai-factory", "version": "1.1.307"},
            })
            self._notify("notifications/initialized", {})
            if isinstance(init, dict) and init.get("protocolVersion"):
                self._ready = True
            else:
                raise McpError(f"initialize 响应异常: {init}")
        except Exception as exc:  # noqa: BLE001
            self.stop()
            raise McpError(f"MCP server {self.name} 启动失败: {exc}") from exc

    def stop(self) -> None:
        self._ready = False
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    self._proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            self._proc = None

    # ------------------------------------------------------------ 帧读写
    def _write_frame(self, payload: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise McpError("MCP 进程未启动")
        data = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8")
        try:
            self._proc.stdin.write(header + data)
            self._proc.stdin.flush()
        except Exception as exc:  # noqa: BLE001
            raise McpError(f"MCP 写入失败: {exc}") from exc

    def _read_frame(self) -> dict[str, Any] | None:
        if self._proc is None or self._proc.stdout is None:
            raise McpError("MCP 进程未启动")
        import select
        import time

        deadline = time.monotonic() + _READ_TIMEOUT
        while True:
            # 找 Content-Length 头
            if b"\r\n\r\n" in self._buffer:
                head, rest = self._buffer.split(b"\r\n\r\n", 1)
                m = None
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        m = int(line.split(b":", 1)[1].strip())
                if m is None:
                    raise McpError("MCP 帧缺 Content-Length")
                if len(rest) >= m:
                    body = rest[:m]
                    self._buffer = rest[m:]
                    try:
                        return json.loads(body.decode("utf-8"))
                    except Exception as exc:  # noqa: BLE001
                        raise McpError(f"MCP 帧 JSON 解析失败: {exc}") from exc
            # select 可读等待 (阻塞 read 无法被 deadline 中断 → 用 select)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpError("MCP 读取超时")
            ready, _, _ = select.select([self._proc.stdout], [], [], remaining)
            if not ready:
                raise McpError("MCP 读取超时")
            # read1: 只读一次返回可用字节 (read(n) 在 buffered pipe 上会等满 n 阻塞)
            chunk = self._proc.stdout.read1(4096)
            if not chunk:
                raise McpError("MCP 进程退出")
            self._buffer += chunk

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = str(uuid.uuid4())
        with self._lock:
            self._write_frame({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            while True:
                frame = self._read_frame()
                if frame is None:
                    continue
                if frame.get("id") != req_id:
                    continue  # 跳过 notification/其他响应
                if frame.get("error"):
                    raise McpError(f"MCP {method} 错误: {frame['error']}")
                return frame.get("result") or {}

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        with self._lock:
            self._write_frame({"jsonrpc": "2.0", "method": method, "params": params})

    # ------------------------------------------------------------ 工具面
    def list_tools(self) -> list[dict[str, Any]]:
        self.start()
        result = self._request("tools/list", {})
        out = []
        for t in result.get("tools") or []:
            out.append({
                "name": str(t.get("name") or ""),
                "description": str(t.get("description") or ""),
                "inputSchema": t.get("inputSchema") or {"type": "object", "properties": {}},
            })
        return out

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self.start()
        result = self._request("tools/call", {
            "name": name, "arguments": arguments or {},
        })
        # MCP 内容块 → 文本
        texts = []
        for block in result.get("content") or []:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    texts.append(str(block["text"]))
                elif block.get("type") == "resource" and block.get("resource"):
                    texts.append(str(block["resource"]))
            elif isinstance(block, str):
                texts.append(block)
        is_error = bool(result.get("isError"))
        return {"ok": not is_error, "output": "\n".join(texts),
                "error": "" if not is_error else "\n".join(texts) or "MCP 工具调用失败"}


#: 进程内 MCP 客户端缓存 (按 data_dir) — 避免每轮重启
_clients: dict[str, dict[str, McpClient]] = {}


def load_mcp_servers(data_dir: str | None) -> dict[str, McpClient]:
    """从 <data_dir>/mcp_servers.json 加载/缓存 MCP clients。

    配置格式: {"servers": {"name": {"command": "...", "args": [...]}}}
    失败: 单个 server 配置坏 → 跳过, 不拖垮。
    """
    key = str(data_dir or "")
    if key in _clients:
        return _clients[key]
    out: dict[str, McpClient] = {}
    if data_dir:
        try:
            import os
            from pathlib import Path

            p = Path(data_dir) / "mcp_servers.json"
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                for name, cfg in (d.get("servers") or {}).items():
                    if isinstance(cfg, dict) and cfg.get("command"):
                        out[str(name)] = McpClient(str(name), str(cfg["command"]),
                                                   [str(a) for a in (cfg.get("args") or [])])
        except Exception:  # noqa: BLE001 — 配置坏 → 空 (不崩)
            pass
    _clients[key] = out
    return out
