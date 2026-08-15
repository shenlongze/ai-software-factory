"""factory-console/session/workspace.py — WorkspaceContext (S10-056 批次 A)。

共享项目上下文 (设计 §2.5): 让 Agent 知道 之前谁做过什么 —
{project, files[], completed_tasks[], artifacts[], agent_history[]},
落盘 projects/<slug>/workspace_context.json (~/.factory/)。

组件:
- WorkspaceContext — init(project) / add_file / mark_task_completed /
  add_artifact / snapshot(project_dir) / save(project_dir, ctx) /
  load(project_dir) (失败安全: 缺文件 → 空 context)

设计: docs/sprint10/S10-056-team-design.md §2.5 / §4
边界:
- 纯标准库 (json/pathlib), 零模块依赖; 失败安全 (缺失/损坏 → 空 context)
- 变更方法 (add_*) 读-改-落盘-返回: 幂等追加 (文件/任务/产物去重;
  agent_history 为日志, 只追加)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

#: 上下文文件名 (project_dir/workspace_context.json — 设计 §4 资产口径)
WORKSPACE_CONTEXT_FILE_NAME = "workspace_context.json"


class WorkspaceContext:
    """共享项目上下文 (设计 §2.5): 全部字段落盘 workspace_context.json。

    init(project) → 空上下文 {project, files[], completed_tasks[],
    artifacts[], agent_history[]}; add_file/mark_task_completed/add_artifact
    读-改-落盘-返回 (幂等去重); snapshot(project_dir) → 当前上下文拷贝;
    save(project_dir, ctx) 显式落盘; load(project_dir) 失败安全 (缺文件 →
    空上下文, 不抛)。
    """

    FILE_NAME = WORKSPACE_CONTEXT_FILE_NAME

    # ------------------------------------------------------------ 构造

    @staticmethod
    def init(project: str) -> dict[str, Any]:
        """空上下文 (设计 §2.5 全字段骨架)。"""
        return {
            "project": str(project),
            "files": [],
            "completed_tasks": [],
            "artifacts": [],
            "agent_history": [],
        }

    @classmethod
    def _normalize(cls, data: Any, project_dir: Path) -> dict[str, Any]:
        """任意结构 → 全字段上下文 (缺字段 → 空列表; 非 dict → 空上下文)。"""
        if not isinstance(data, dict):
            return cls.init("")
        project = str(data.get("project") or "")
        ctx = cls.init(project)
        ctx["files"] = [
            str(f) for f in (data.get("files") or []) if not isinstance(f, dict)
        ]
        ctx["completed_tasks"] = [
            str(t) for t in (data.get("completed_tasks") or []) if not isinstance(t, dict)
        ]
        ctx["artifacts"] = [
            str(a) for a in (data.get("artifacts") or []) if not isinstance(a, dict)
        ]
        history = data.get("agent_history") or []
        ctx["agent_history"] = [dict(h) for h in history if isinstance(h, dict)]
        return ctx

    # ------------------------------------------------------------ 读写

    @classmethod
    def _file(cls, project_dir: Any) -> Path:
        return Path(project_dir) / cls.FILE_NAME

    @classmethod
    def load(cls, project_dir: Any) -> dict[str, Any]:
        """读 workspace_context.json → 上下文; 缺失/损坏 → 空上下文 (失败安全)。"""
        path = cls._file(project_dir)
        data: Any = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空上下文
            data = None
        return cls._normalize(data, path.parent)

    @classmethod
    def save(cls, project_dir: Any, ctx: dict[str, Any]) -> Path:
        """落盘 workspace_context.json (父目录自动创建; 中文可读)。"""
        path = cls._file(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cls._normalize(ctx, path.parent), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def snapshot(cls, project_dir: Any) -> dict[str, Any]:
        """当前上下文深拷贝 (改返回值不影响落盘状态)。"""
        ctx = cls.load(project_dir)
        return {
            k: [dict(h) for h in v] if k == "agent_history" else list(v)
            for k, v in ctx.items()
        }

    # ------------------------------------------------------------ 变更 (幂等)

    @classmethod
    def add_file(cls, project_dir: Any, path: str) -> dict[str, Any]:
        """记录项目文件 (去重) → 落盘 → 返回上下文。"""
        ctx = cls.load(project_dir)
        entry = str(path)
        if entry not in ctx["files"]:
            ctx["files"].append(entry)
            cls.save(project_dir, ctx)
        return ctx

    @classmethod
    def mark_task_completed(
        cls, project_dir: Any, task: str, agent: str, result: str
    ) -> dict[str, Any]:
        """任务完成: completed_tasks 追加 (去重) + agent_history 日志追加 → 落盘。"""
        ctx = cls.load(project_dir)
        task_id = str(task)
        if task_id not in ctx["completed_tasks"]:
            ctx["completed_tasks"].append(task_id)
        ctx["agent_history"].append(
            {"agent": str(agent), "task": task_id, "result": str(result)}
        )
        cls.save(project_dir, ctx)
        return ctx

    @classmethod
    def add_artifact(cls, project_dir: Any, artifact: str) -> dict[str, Any]:
        """记录产物 (去重) → 落盘 → 返回上下文。"""
        ctx = cls.load(project_dir)
        entry = str(artifact)
        if entry not in ctx["artifacts"]:
            ctx["artifacts"].append(entry)
            cls.save(project_dir, ctx)
        return ctx
