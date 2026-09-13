"""events/logger.py — 高层 API: 线程安全的统一事件入口。

设计依据: phase1-plan.md §6 — 全项目只通过 EventLogger 发事件;
线程安全由内部 Lock 串行化写入 (单进程内, SQLite WAL 支持多读单写)。
"""

from __future__ import annotations

import threading
from typing import Any

from .models import Event, EventType
from .store import EventStore


class EventLogger:
    """线程安全的统一入口。全项目只通过它发事件。"""

    def __init__(self, store: EventStore):
        self._store = store
        self._lock = threading.Lock()

    @property
    def store(self) -> EventStore:
        return self._store

    def record(
        self,
        type_: EventType | str,
        *,
        source: str,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        stage: str | None = None,
        action: str | None = None,
        result: str | None = None,
        evidence: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        """通用记录: 构造 Event 并追加 (事件先落库, 再由发布方执行后续动作)。"""
        event = Event.create(
            type_,
            source=source,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            stage=stage,
            action=action,
            result=result,
            evidence=evidence,
            payload=payload,
        )
        with self._lock:
            return self._store.append(event)

    # ------------------------------------------------------------------ 六类便捷方法

    def task_start(
        self, task_id: str, title: str, role: str, *,
        project_id: str | None = None, agent_id: str | None = None, source: str = "orchestrator",
    ) -> Event:
        return self.record(
            EventType.TASK_START, source=source, project_id=project_id,
            task_id=task_id, agent_id=agent_id, stage="running", action="start task", result="OK",
            payload={"title": title, "role": role},
        )

    def task_end(
        self, task_id: str, result: str, duration_s: float, artifact: str | None = None, *,
        project_id: str | None = None, agent_id: str | None = None, source: str = "orchestrator",
    ) -> Event:
        return self.record(
            EventType.TASK_END, source=source, project_id=project_id,
            task_id=task_id, agent_id=agent_id, stage="done", action="finish task", result=result,
            payload={"result": result, "duration_s": duration_s, "artifact": artifact},
        )

    def task_fail(
        self, task_id: str, stage: str, error: str, evidence: str | None = None, *,
        project_id: str | None = None, agent_id: str | None = None, source: str = "orchestrator",
    ) -> Event:
        return self.record(
            EventType.TASK_FAIL, source=source, project_id=project_id,
            task_id=task_id, agent_id=agent_id, stage="failed", action="task failed",
            result="failed", evidence=evidence,
            payload={"stage": stage, "error": error, "evidence": evidence},
        )

    def tool_call(
        self, task_id: str, tool: str, arg_summary: str, result_summary: str, duration_s: float, *,
        project_id: str | None = None, agent_id: str | None = None, source: str = "orchestrator",
    ) -> Event:
        return self.record(
            EventType.TOOL_CALL, source=source, project_id=project_id,
            task_id=task_id, agent_id=agent_id, stage="running", action=tool, result="OK",
            payload={"tool": tool, "arg_summary": arg_summary,
                     "result_summary": result_summary, "duration_s": duration_s},
        )

    def checkpoint(
        self, task_id: str, description: str, artifacts: list[str] | None = None, *,
        project_id: str | None = None, agent_id: str | None = None, source: str = "orchestrator",
    ) -> Event:
        return self.record(
            EventType.CHECKPOINT, source=source, project_id=project_id,
            task_id=task_id, agent_id=agent_id, stage="checkpoint", action=description, result="OK",
            payload={"description": description, "artifacts": artifacts or []},
        )

    def session_close(
        self, session_id: str, *,
        project_id: str | None = None, agent_id: str | None = None, source: str = "orchestrator",
    ) -> Event:
        return self.record(
            EventType.SESSION_CLOSE, source=source, project_id=project_id,
            agent_id=agent_id, stage="closed", action="close session", result="OK",
            payload={"session_id": session_id},
        )
