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
                    error: str = "", kind: str = "llm_raw",
                    model: str = "", provider: str = "",
                    prompt_tokens: int = 0, completion_tokens: int = 0,
                    cost_usd: float | None = None) -> None:
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
            # ★ 记"这次用了哪个模型/供应商"（2026-09-14 ✓ Founder 问"真的好了么/正常使用么"）
            #   原留痕只记 prompt/resp/耗时 ✗ → "底层改了配置实际用的是不是它"【无法自证 ✗】
            #   → 记上后【一眼可验 ✓】+ 可按模型统计用量/成本 ✓
            "model": model,
            "provider": provider,
            # ★ R1（2026-09-14 ✓ Founder: "需要有成本统计、llm 使用监控、log"）
            #   真 tokens + 成本估算 —— 来源 = gateway 已算好的 usage ✓（不重算 ✗ 不臆造 ✗）
            #   缺价时 cost_usd=None ✓（诚实缺失 ✓ 不填 0 假账 ✓）
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "total_tokens": int((prompt_tokens or 0) + (completion_tokens or 0)),
            "cost_usd": cost_usd,
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


def is_measured(rec: dict) -> bool:
    """这条留痕是否【真采集到用量】(R2 ✓ 2026-09-15)。

    ★ 两类写入方不能混 ✗（同文件多写入方 ✓）:
      · llm_gateway.py:413（kind=llm_complete ✓ 唯一汇聚点）→ 真 tokens + cost ✓
      · console_sessions.py:111（kind=llm_raw ✗）→ 不传 tokens → 默认 0 ✗
    默认 0 会被读成「这次调用 0 tokens」= 【假账 ✗】（其实是【没采集】✓）
    ⇒ 判据: 有 tokens 字段 且（tokens>0 或 成本已记）→ 才算【已计量】✓
    """
    if "prompt_tokens" not in rec:
        return False          # R1 之前的老记录（无 tokens 字段 ✓）
    return bool(rec.get("prompt_tokens") or rec.get("completion_tokens")
                or rec.get("cost_usd") is not None)


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
