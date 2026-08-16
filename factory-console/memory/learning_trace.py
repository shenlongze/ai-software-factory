"""factory-console/memory/learning_trace.py — LearningTrace (S10-067 G8)。

学习过程审计: 学习来源/提取内容/confidence/影响范围 → learning_trace.json
(workspace/memory/) — 可解释性资产 (S10-069 审计基础)。

设计: docs/sprint10/S10-067-memory-learning-design.md §6
边界:
- 纯标准库 (json/uuid/datetime/pathlib), 零模块依赖
- 失败安全: 缺失/损坏 → []; 落盘异常 → 静默 (不中断学习流)
- 只追加 (审计日志语义 — 不修改历史条目)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .experience_store import memory_dir

#: 审计文件名 (workspace/memory/learning_trace.json)
LEARNING_TRACE_FILE_NAME = "learning_trace.json"


def learning_trace_file(workspace: Any = None) -> Path:
    """workspace/memory/learning_trace.json (缺省工厂根)。"""
    return memory_dir(workspace) / LEARNING_TRACE_FILE_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningTrace:
    """学习审计 (G8): record() → learning_trace.json (只追加, 失败安全)。

    record(source, learned, confidence, impact, details) → 审计条目:
      {trace_id, source, learned, confidence, impact, details, created_at}
    records() → 全部审计条目 (缺失/损坏 → [] 失败安全)。
    """

    def __init__(self, workspace: Any = None, path: Any = None) -> None:
        self.path: Path = (
            Path(path) if path is not None else learning_trace_file(workspace)
        )

    def record(
        self,
        source: str,
        learned: Any,
        confidence: float,
        impact: str,
        details: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """记录一次学习事件 (审计): 来源/内容/置信/影响 → 落盘 → 返回条目。"""
        entry: dict[str, Any] = {
            "trace_id": f"trace-{uuid.uuid4().hex[:12]}",
            "source": str(source or ""),
            "learned": learned,
            "confidence": confidence,
            "impact": str(impact or ""),
            "details": dict(details) if isinstance(details, dict) else {},
            "created_at": _now_iso(),
        }
        entries = self.records()
        entries.append(entry)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断学习流
            pass
        return entry

    def records(self) -> list[dict[str, Any]]:
        """全部审计条目 (缺失/损坏 → [] 失败安全)。"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全
            return []
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []
