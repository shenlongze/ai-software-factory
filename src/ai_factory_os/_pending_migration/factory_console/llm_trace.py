"""llm_trace — LLM 调用留痕（"思考过程"的可审计记录）。

为什么（Founder 指出的缺口 ✓）:
  系统记录了【做了什么】(execution report ✓ patch ✓ 成本 ✓)，
  但【没记录 LLM 当时想了什么】✗ —— 原始 prompt / 原始输出 无留痕 ✗。
  对「可审计 / 可复盘 / 可教学 / 可改进」这是缺的 ✓。

设计（克制 ✓）:
  · append-only JSONL: <data_root>/traces/llm.jsonl ✓（一行一次调用 ✓ 便于 grep/jq ✓）
  · 每条截断（prompt/response 各 4KB ✓）→ 不因长 prompt 撑爆存储 ✓
  · 失败安全: 任何异常都吞掉 ✓（留痕【绝不能】影响主链 ✓）
  · 可关闭: 环境变量 HERMES_HMM 无 —— 用 FACTORY_LLM_TRACE=0 关闭 ✓
  · 不记录密钥: 只记 prompt/response 文本本身（调用方不应把 key 放 prompt ✓）
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_MAX_FIELD = 4096


def trace_root() -> Path:
    """数据根（与 CLI 的 data_dir 默认一致 ✓）。"""
    env = os.environ.get("FACTORY_DATA_DIR") or os.environ.get("DATA_DIR")
    return Path(env) if env else (Path.home() / ".factory")


def trace_path() -> Path:
    return trace_root() / "traces" / "llm.jsonl"


def record_llm_call(prompt: str, response: str | None, *,
                    duration_s: float | None = None,
                    error: str = "", kind: str = "llm_raw") -> None:
    """追加一条 LLM 调用记录（失败安全 ✓ 绝不影响调用方 ✓）。"""
    if os.environ.get("FACTORY_LLM_TRACE", "1") == "0":
        return
    try:
        rec: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kind": kind,
            "prompt_chars": len(prompt or ""),
            "response_chars": len(response or ""),
            "duration_s": round(duration_s, 3) if duration_s is not None else None,
            "prompt": (prompt or "")[:_MAX_FIELD],
            "response": (response or "")[:_MAX_FIELD],
        }
        if error:
            rec["error"] = error[:500]
        p = trace_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with _LOCK:
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:  # noqa: BLE001 — 留痕失败绝不影响主链 ✓
        pass


def stats() -> dict[str, Any]:
    """trace 概况（供 CLI 展示 ✓）。"""
    p = trace_path()
    if not p.is_file():
        return {"exists": False, "path": str(p), "calls": 0}
    calls = 0
    bytes_ = 0
    last = ""
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    calls += 1
        bytes_ = p.stat().st_size
        with p.open(encoding="utf-8") as f:
            tail = f.readlines()[-1:]
        if tail:
            last = str(json.loads(tail[0]).get("ts") or "")
    except Exception:  # noqa: BLE001
        pass
    return {"exists": True, "path": str(p), "calls": calls,
            "bytes": bytes_, "last": last}
