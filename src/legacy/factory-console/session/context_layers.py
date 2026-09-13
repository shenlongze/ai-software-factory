"""factory-console/session/context_layers.py — L0/L1/L2 分层上下文加载 (S10-127 P1.3).

参考 OpenViking (AGPL, 只借鉴设计): 摘要 → 概览 → 详情按需取, 不一次全塞。
- L0 (Abstract): 项目一句话 — 当前目标 + 最近归档任务标题 (快速判断相关性, ~100 token)
- L1 (Overview): + 交接面 + 有效需求 + 最近记忆 (规划/继续做 XX 用, ~400 token)
- L2 (Details): + 完整归档记忆 + 更多记忆 + 证据指针 (深任务用)

按模型能力选深度:
- 弱模型/小窗口 → L1 (够用且省 token); 极端小 (<16k) → L0
- 强模型/大窗口 → L2
失败安全: 任何一层缺失 → 跳过, 不崩。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

#: 极端小上下文 → 只 L0
TINY_CONTEXT = 16_000


def pick_depth(model_tier: str | None = None, context_window: int | None = None) -> str:
    """按模型能力选注入深度: "l0" | "l1" | "l2"。"""
    try:
        if context_window is not None and int(context_window) < TINY_CONTEXT:
            return "l0"
    except Exception:  # noqa: BLE001
        pass
    if model_tier == "light":
        return "l1"
    return "l2"


def _load_spine(data_dir: str | Path, project_id: str):
    from .handoff import ProjectSpine

    return ProjectSpine.load(data_dir, project_id)


def _load_memory(data_dir: str | Path, project_id: str):
    from .project_memory import MemoryStore

    return MemoryStore.load(data_dir, project_id)


def _l0(sp: Any) -> str:
    lines: list[str] = []
    goal = sp.data.get("current_goal") or {}
    if goal.get("text"):
        lines.append(f"当前目标: {goal['text']}")
    cls = sp.data.get("closure_memory") or []
    if cls:
        lines.append("已归档: " + " · ".join(str(c.get("title") or "")[:30] for c in cls[-3:]))
    return "\n".join(lines)


def _l1(sp: Any, mem: Any, query: str | None = None) -> str:
    # L1: 复用 M3 权威分层 (≥repo_evidence), 少带记忆 (弱模型省 token; T9 相关优先)
    parts = [sp.view(min_authority=3), mem.inject_block(3, query=query)]
    return "\n".join(x for x in parts if x)


def _l2(sp: Any, mem: Any, query: str | None = None) -> str:
    # L2: 全量 Spine 视图 + 更多记忆 (强模型/深任务; T9 相关优先)
    parts = [sp.view(), mem.inject_block(8, query=query)]
    return "\n".join(x for x in parts if x)


def build_context(data_dir: str | Path, project_id: str, *, depth: str = "l1", query: str | None = None) -> str:
    """按 depth 组装分层上下文块 (无数据 → 空串; query → 记忆相关召回)。"""
    if not data_dir or not project_id:
        return ""
    try:
        sp = _load_spine(data_dir, project_id)
        mem = _load_memory(data_dir, project_id)
        parts: list[str] = []
        l0 = _l0(sp)
        if l0:
            parts.append(l0)
        if depth in ("l1", "l2"):
            l1 = _l1(sp, mem, query=query)
            if l1:
                parts.append(l1)
        if depth == "l2":
            l2 = _l2(sp, mem, query=query)
            if l2:
                parts.append(l2)
        if not parts:
            return ""
        return "【项目上下文】(" + depth.upper() + ")\n" + "\n".join(parts)
    except Exception:  # noqa: BLE001 — 任一缺失 → 空 (不崩)
        return ""
