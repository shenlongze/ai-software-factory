"""factory-console/exec_checkpoint.py — T-6 (v1.1.187): 执行中断 checkpoint 落盘与恢复。

Founder 2026-08-27 (D-2/T-6): 执行中断 checkpoint 恢复实测 —
进程被杀/断电后, 进行中执行有 checkpoint 可查、可恢复 (续跑), 不丢状态。

- 启动执行 (start_task_exec) → 写 checkpoint (exec/checkpoints.json: task_id →
  {exec_ref, project_id, started_at, stage, note}); 进程崩溃 checkpoint 仍在
- 结束执行 (finish_task_exec) → 清除 checkpoint
- 失败安全: 文件缺失/损坏 → 空 (不阻断); 写失败 → 静默 (尽力而为)
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ExecCheckpointStore:
    """执行 checkpoint (data_dir/exec/checkpoints.json) — 中断可恢复可见。"""

    def __init__(self, root: str | Path):
        self._path = Path(root) / "exec" / "checkpoints.json"
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:  # 不可写 → 静默 (checkpoint 尽力而为)
            pass

    def start(
        self,
        task_id: str,
        *,
        exec_ref: str = "",
        project_id: str = "",
        note: str = "",
    ) -> dict[str, Any] | None:
        """执行启动 → 写 checkpoint (进程崩溃后仍可查可恢复)。"""
        task_id = str(task_id or "").strip()
        if not task_id:
            return None
        with self._lock:
            data = self._load()
            entry = {
                "task_id": task_id,
                "project_id": str(project_id or ""),
                "exec_ref": str(exec_ref or ""),
                "started_at": _now_iso(),
                "stage": "executing",
                "note": str(note or ""),
            }
            data[task_id] = entry
            self._save(data)
            return dict(entry)

    def finish(self, task_id: str) -> None:
        """执行结束 → 清除 checkpoint。"""
        task_id = str(task_id or "").strip()
        if not task_id:
            return
        with self._lock:
            data = self._load()
            data.pop(task_id, None)
            self._save(data)

    def get(self, task_id: str) -> dict[str, Any] | None:
        task_id = str(task_id or "").strip()
        if not task_id:
            return None
        entry = self._load().get(task_id)
        return dict(entry) if entry else None

    def list(self) -> list[dict[str, Any]]:
        """全部进行中/中断的执行 (按 started_at 倒序)。"""
        items = list(self._load().values())
        items.sort(key=lambda e: e.get("started_at") or "", reverse=True)
        return items
