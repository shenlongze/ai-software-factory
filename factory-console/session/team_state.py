"""factory-console/session/team_state.py — TeamExecutionState (S10-057 P1)。

团队执行状态 (设计 §P1): team_execution_state.json 落盘 projects/<slug>/ —
{team, status, started_at, updated_at, tasks: {task_id: {agent, status, artifact}},
validation}, 支持暂停/恢复/进度查询。

组件:
- TeamExecutionState — init(project_dir, team_id, tasks) / update(project_dir,
  task_id, status, agent?, artifact?) / get() / snapshot() / save() / load()
  (失败安全: 缺失/损坏 → None) / pause() / resume() / is_paused() /
  progress() / set_status()

设计: docs/sprint10/S10-057-team-production-design.md §P1 / §2 数据资产
边界:
- 纯标准库 (json/pathlib), 零模块依赖; 失败安全, 永不抛
- 团队级状态: status ∈ running/paused/completed/failed;
  任务级状态: status ∈ pending/running/completed/failed
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 团队执行状态文件名 (project_dir/team_execution_state.json — 设计 §4 资产口径)
TEAM_EXECUTION_STATE_FILE_NAME = "team_execution_state.json"

#: 团队级状态常量
TEAM_STATUS_RUNNING = "running"
TEAM_STATUS_PAUSED = "paused"
TEAM_STATUS_COMPLETED = "completed"
TEAM_STATUS_FAILED = "failed"

#: 任务级状态常量
TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (状态变更时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


class TeamExecutionState:
    """团队执行状态 (设计 §P1): team_execution_state.json 读-改-落盘 + 暂停/恢复。

    init(project_dir, team_id, tasks): 全新状态 — {team, status: "running",
    started_at, updated_at, tasks: {task_id: {agent, status: "pending",
    artifact: ""}}, validation: None} → 落盘。
    update(project_dir, task_id, status, agent?, artifact?): 单任务状态更新
    (未知任务 → 追加, 失败安全) → 落盘 → 返回状态。
    pause/resume/is_paused: 团队级暂停/恢复 (status: paused/running)。
    progress(project_dir): {total, completed, running, pending, failed,
    percent, status, paused} 只读统计。
    get/snapshot: 读取 (缺失/损坏 → 缺省骨架, 不抛); load: 缺失 → None。
    """

    FILE_NAME = TEAM_EXECUTION_STATE_FILE_NAME

    STATUS_RUNNING = TEAM_STATUS_RUNNING
    STATUS_PAUSED = TEAM_STATUS_PAUSED
    STATUS_COMPLETED = TEAM_STATUS_COMPLETED
    STATUS_FAILED = TEAM_STATUS_FAILED

    TASK_PENDING = TASK_STATUS_PENDING
    TASK_RUNNING = TASK_STATUS_RUNNING
    TASK_COMPLETED = TASK_STATUS_COMPLETED
    TASK_FAILED = TASK_STATUS_FAILED

    # ------------------------------------------------------------ 构造

    @classmethod
    def _file(cls, project_dir: Any) -> Path:
        return Path(project_dir) / cls.FILE_NAME

    @classmethod
    def _normalize(cls, data: Any, project_dir: Path) -> dict[str, Any]:
        """任意结构 → 全字段状态骨架 (缺字段 → 缺省, 失败安全)。"""
        if not isinstance(data, dict):
            return cls._default(str(Path(project_dir).name))
        tasks: dict[str, dict[str, Any]] = {}
        raw_tasks = data.get("tasks") or {}
        if isinstance(raw_tasks, dict):
            for tid, raw in raw_tasks.items():
                if not isinstance(raw, dict):
                    raw = {}
                tasks[str(tid)] = {
                    "agent": str(raw.get("agent") or ""),
                    "status": str(raw.get("status") or TASK_STATUS_PENDING),
                    "artifact": str(raw.get("artifact") or ""),
                }
        elif isinstance(raw_tasks, list):  # 前向兼容: 列表 → 按 id 索引
            for raw in raw_tasks:
                if not isinstance(raw, dict):
                    continue
                tid = str(raw.get("id") or "")
                if not tid:
                    continue
                tasks[tid] = {
                    "agent": str(raw.get("agent") or ""),
                    "status": str(raw.get("status") or TASK_STATUS_PENDING),
                    "artifact": str(raw.get("artifact") or ""),
                }
        validation = data.get("validation")
        return {
            "team": str(data.get("team") or ""),
            "status": str(data.get("status") or TEAM_STATUS_RUNNING),
            "started_at": str(data.get("started_at") or ""),
            "updated_at": str(data.get("updated_at") or ""),
            "tasks": tasks,
            "validation": validation if isinstance(validation, dict) else None,
        }

    @classmethod
    def _default(cls, team: str = "") -> dict[str, Any]:
        """缺省状态骨架 (团队级 running — 失败安全)。"""
        return {
            "team": str(team),
            "status": TEAM_STATUS_RUNNING,
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
            "tasks": {},
            "validation": None,
        }

    # ------------------------------------------------------------ init/读写

    @classmethod
    def init(
        cls, project_dir: Any, team_id: str, tasks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """全新状态: 任务全 pending (agent 取自任务 agent 字段) → 落盘 → 返回。"""
        now = _now_iso()
        state: dict[str, Any] = {
            "team": str(team_id),
            "status": TEAM_STATUS_RUNNING,
            "started_at": now,
            "updated_at": now,
            "tasks": {
                str(t.get("id") or ""): {
                    "agent": str(t.get("agent") or ""),
                    "status": TASK_STATUS_PENDING,
                    "artifact": "",
                }
                for t in (tasks or [])
                if t.get("id")
            },
            "validation": None,
        }
        cls.save(project_dir, state)
        return state

    @classmethod
    def save(cls, project_dir: Any, state: dict[str, Any]) -> Path:
        """落盘 team_execution_state.json (父目录自动创建; 中文可读)。"""
        path = cls._file(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cls._normalize(state, path.parent), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, project_dir: Any) -> Optional[dict[str, Any]]:
        """读 team_execution_state.json → 状态; 缺失 → None (失败安全)。"""
        path = cls._file(project_dir)
        if not path.is_file():
            return None
        data: Any = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 损坏 → None
            return None
        return cls._normalize(data, path.parent)

    @classmethod
    def get(cls, project_dir: Any) -> dict[str, Any]:
        """读取状态; 缺失/损坏 → 缺省骨架 (不抛, 失败安全)。"""
        state = cls.load(project_dir)
        if state is None:
            return cls._default(str(Path(project_dir).name))
        return state

    @classmethod
    def snapshot(cls, project_dir: Any) -> dict[str, Any]:
        """当前状态深拷贝 (改返回值不影响落盘状态)。"""
        state = cls.get(project_dir)
        return {
            "team": state["team"],
            "status": state["status"],
            "started_at": state["started_at"],
            "updated_at": state["updated_at"],
            "tasks": {
                tid: dict(entry) for tid, entry in state["tasks"].items()
            },
            "validation": (
                dict(state["validation"]) if state.get("validation") else None
            ),
        }

    # ------------------------------------------------------------ 变更

    @classmethod
    def update(
        cls,
        project_dir: Any,
        task_id: str,
        status: str,
        agent: Optional[str] = None,
        artifact: Optional[str] = None,
    ) -> dict[str, Any]:
        """单任务状态更新 (未知任务 → 追加, 失败安全) → 落盘 → 返回状态。"""
        state = cls.get(project_dir)
        key = str(task_id or "")
        entry = state["tasks"].setdefault(
            key, {"agent": "", "status": TASK_STATUS_PENDING, "artifact": ""}
        )
        entry["status"] = str(status or entry.get("status") or TASK_STATUS_PENDING)
        if agent is not None:
            entry["agent"] = str(agent)
        if artifact is not None:
            entry["artifact"] = str(artifact)
        state["updated_at"] = _now_iso()
        cls.save(project_dir, state)
        return state

    @classmethod
    def set_status(cls, project_dir: Any, status: str) -> dict[str, Any]:
        """团队级状态落盘 (running/paused/completed/failed) → 返回状态。"""
        state = cls.get(project_dir)
        state["status"] = str(status or TEAM_STATUS_RUNNING)
        state["updated_at"] = _now_iso()
        cls.save(project_dir, state)
        return state

    @classmethod
    def pause(cls, project_dir: Any) -> dict[str, Any]:
        """暂停: 团队状态 → paused → 落盘 → 返回状态 (缺失 → 缺省骨架, 不抛)。"""
        return cls.set_status(project_dir, TEAM_STATUS_PAUSED)

    @classmethod
    def resume(cls, project_dir: Any) -> dict[str, Any]:
        """恢复: 团队状态 → running → 落盘 → 返回状态 (缺失 → 缺省骨架, 不抛)。"""
        return cls.set_status(project_dir, TEAM_STATUS_RUNNING)

    @classmethod
    def is_paused(cls, project_dir: Any) -> bool:
        """团队是否处于暂停 (缺失/损坏 → False, 失败安全)。"""
        return cls.get(project_dir).get("status") == TEAM_STATUS_PAUSED

    # ------------------------------------------------------------ 进度

    @classmethod
    def progress(cls, project_dir: Any) -> dict[str, Any]:
        """进度统计 (只读): {total, completed, running, pending, failed,
        percent (0-100 整数), status, paused}。"""
        state = cls.get(project_dir)
        tasks = state["tasks"]
        total = len(tasks)
        counts = {
            TASK_STATUS_COMPLETED: 0,
            TASK_STATUS_RUNNING: 0,
            TASK_STATUS_PENDING: 0,
            TASK_STATUS_FAILED: 0,
        }
        for entry in tasks.values():
            status = str(entry.get("status") or TASK_STATUS_PENDING)
            if status in counts:
                counts[status] += 1
        completed = counts[TASK_STATUS_COMPLETED]
        percent = round(completed * 100 / total) if total else 0
        return {
            "total": total,
            "completed": completed,
            "running": counts[TASK_STATUS_RUNNING],
            "pending": counts[TASK_STATUS_PENDING],
            "failed": counts[TASK_STATUS_FAILED],
            "percent": percent,
            "status": state["status"],
            "paused": state["status"] == TEAM_STATUS_PAUSED,
        }
