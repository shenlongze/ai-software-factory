"""factory-console/external_executor/task_registry.py — 外部任务控制面 (网关 G2).

对标 OpenClaw tasks 控制面 (SQLite 注册表): 外部执行任务的统一持久化注册表。
落盘 <data_dir>/exec/external_tasks.json:
  tasks: {TASK-GW-xxx: {id, status, owner, project_id, task, started_at, finished_at,
                        retry_count, result_id, verify, audit[]}}

status: running → done | failed (重试时 running→retry→running)
失败安全: 文件坏/缺失 → 空注册表; 写入 OSError 静默。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"TASK-GW-{uuid.uuid4().hex[:8]}"


class ExternalTaskRegistry:
    def __init__(self, data_dir: str | Path | None, data: dict[str, Any] | None = None):
        self.data_dir = data_dir
        self.tasks: dict[str, dict[str, Any]] = dict((data or {}).get("tasks") or {})

    @classmethod
    def load(cls, data_dir: str | Path | None) -> "ExternalTaskRegistry":
        st = cls(data_dir)
        if not data_dir:
            return st
        try:
            d = json.loads((Path(data_dir) / "exec" / "external_tasks.json").read_text(encoding="utf-8"))
            st.tasks = dict((d.get("tasks") if isinstance(d, dict) else None) or {})
        except Exception:  # noqa: BLE001 — 坏/缺 → 空 (不崩)
            pass
        return st

    def save(self) -> None:
        if not self.data_dir:
            return
        try:
            path = Path(self.data_dir) / "exec" / "external_tasks.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"tasks": self.tasks}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------ 操作
    def create(self, *, task: str, owner: str, project_id: str = "",
               verify_plan: str = "") -> str:
        tid = _new_id()
        self.tasks[tid] = {
            "id": tid, "status": "running", "owner": str(owner),
            "project_id": str(project_id), "task": str(task)[:300],
            "started_at": _now_iso(), "finished_at": "",
            "retry_count": 0, "result_id": "", "verify": {"result": "unknown"},
            "audit": [{"ts": _now_iso(), "event": "created", "verify_plan": verify_plan}],
        }
        self.save()
        return tid

    def update(self, tid: str, **fields: Any) -> dict[str, Any] | None:
        t = self.tasks.get(tid)
        if t is None:
            return None
        for k, v in fields.items():
            t[k] = v
        self.save()
        return t

    def audit(self, tid: str, event: str, note: str = "") -> None:
        t = self.tasks.get(tid)
        if t is None:
            return
        t.setdefault("audit", []).append({"ts": _now_iso(), "event": event, "note": str(note)[:200]})
        self.save()

    def get(self, tid: str) -> dict[str, Any] | None:
        t = self.tasks.get(tid)
        return dict(t) if t else None

    def list(self, *, project_id: str = "", status: str = "") -> list[dict[str, Any]]:
        out = []
        for t in self.tasks.values():
            if project_id and t.get("project_id") != project_id:
                continue
            if status and t.get("status") != status:
                continue
            out.append(dict(t))
        out.sort(key=lambda x: str(x.get("started_at") or ""), reverse=True)
        return out

    def stats(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        retries = 0
        for t in self.tasks.values():
            statuses[t.get("status") or "unknown"] = statuses.get(t.get("status") or "unknown", 0) + 1
            retries += int(t.get("retry_count") or 0)
        return {"total": len(self.tasks), "status": statuses, "total_retries": retries}
