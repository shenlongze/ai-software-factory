"""factory-console/session/debug/debug_trace.py — DebugTrace (S10-068 Part 2, G8)。

Audit-ready 记录: 为什么修 (root_cause/evidence) / 谁修 (agent_id) / 用了什么
经验 (retrieved_experiences) / 为什么换策略 (strategy_history) / 花了多少钱
(cost) / 治理决策 (governance) → workspace/debug_trace.json。

设计: docs/sprint10/S10-068-part2-design.md §7
边界:
- 纯标准库, 零模块依赖; 失败安全: 落盘/读取异常 → 静默 (不中断调试流)
- record 不抛 (任何输入 → 尽力记录; 缺失字段兜底)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ...memory.experience_store import DEFAULT_WORKSPACE

#: 审计追踪文件名 (workspace 级)
DEBUG_TRACE_FILE = "debug_trace.json"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式。"""
    return datetime.now(timezone.utc).isoformat()


def _to_dict(value: Any) -> Any:
    """任意值 → dict (对象 to_dict / 原样)。"""
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def debug_trace_file(workspace: Any = None) -> Path:
    """workspace/debug_trace.json (缺省 → ~/.factory/debug_trace.json)。"""
    root = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
    return root / DEBUG_TRACE_FILE


class DebugTrace:
    """审计追踪 (G8): record(session, *, fallback, governance, cost, tokens,
    latency) → debug_trace.json (append-only 列表, Audit-ready)。"""

    def __init__(self, workspace: Any = None) -> None:
        self._file: Path = debug_trace_file(workspace)

    def record(
        self,
        session: Any,
        *,
        fallback: Any = None,
        governance: Any = None,
        cost: Any = None,
        tokens: Any = None,
        latency: Any = None,
    ) -> dict[str, Any]:
        """会话 → 审计条目 (append 落盘; 返回条目, 失败安全)。"""
        trace_id = str(getattr(session, "trace_id", "") or "")
        if not trace_id:
            trace_id = str(getattr(session, "debug_id", "") or f"trc-{uuid.uuid4().hex[:12]}")
        entry = {
            "trace_id": trace_id,
            "debug_id": str(getattr(session, "debug_id", "") or ""),
            "project_id": str(getattr(session, "project_id", "") or ""),
            "task_id": str(getattr(session, "task_id", "") or ""),
            "agent_id": str(getattr(session, "agent_id", "") or ""),
            "failure_id": str(getattr(session, "failure_id", "") or ""),
            "error_summary": str(getattr(session, "error_summary", "") or ""),
            "error_type": str(getattr(session, "error_type", "") or ""),
            "root_cause": _to_dict(getattr(session, "root_cause", None)),
            "root_cause_confidence": float(
                getattr(session, "root_cause_confidence", 0.0) or 0.0
            ),
            "evidence": list(getattr(session, "evidence", None) or []),
            "retrieved_experiences": [
                _to_dict(r) for r in (getattr(session, "retrieved_experiences", None) or [])
            ],
            "selected_strategy": str(getattr(session, "selected_strategy", "") or ""),
            "attempt_number": int(getattr(session, "attempt_number", 0) or 0),
            "strategy_history": [
                _to_dict(a) for a in (getattr(session, "strategy_history", None) or [])
            ],
            "validation_command": str(getattr(session, "validation_command", "") or ""),
            "validation_result": _to_dict(getattr(session, "validation_result", None)),
            "status": str(getattr(session, "status", "") or ""),
            "budget_usage": dict(getattr(session, "budget_usage", None) or {}),
            "governance": _to_dict(governance),
            "fallback": _to_dict(fallback),
            "cost": float(cost) if cost is not None else None,
            "tokens": int(tokens) if tokens is not None else None,
            "latency": float(latency) if latency is not None else None,
            "recorded_at": _now_iso(),
        }
        entries = self.load()
        entries.append(entry)
        self.save(entries)
        return entry

    def load(self) -> list[dict[str, Any]]:
        """读回全部追踪条目 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全
            return []
        if not isinstance(data, list):
            return []
        return [e for e in data if isinstance(e, dict)]

    def save(self, entries: Any) -> None:
        """整表落盘 (失败安全: 读写异常 → 静默)。"""
        if not isinstance(entries, list):
            entries = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    def file_path(self) -> Path:
        """当前落盘文件路径 (审计/展示)。"""
        return Path(self._file)
