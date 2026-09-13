"""factory-console/session/workspace.py — WorkspaceContext (S10-056 批次 A + S10-059 P2)。

共享项目上下文 (设计 §2.5): 让 Agent 知道 之前谁做过什么 —
{project, files[], completed_tasks[], artifacts[], agent_history[]},
落盘 projects/<slug>/workspace_context.json (~/.factory/)。

S10-059 (Workspace Isolation, P2): 增加 reservation 机制 — 同一文件不能被
两个 Agent 同时拥有写权限:
- acquire_reservation(project_dir, agent, task_id, files) → 成功 {agent,
  task_id, files, acquired_at} / 同文件已被其他 agent 占 → None (BLOCK 信号)
  + workspace_locks.json (locks: {file: {agent, task_id, acquired_at}})
- release_reservation(project_dir, agent, task_id) → 释放该任务锁 +
  changed_files 记录 (释放即变更 — 资产化)
- reserved_files(project_dir) → 当前锁快照
上下文扩展字段: active_agent/active_task/reserved_files/workspace_snapshot/
changed_files (经 _normalize 注入 — init 保持 5 字段向后兼容, 精确键断言)。

组件:
- WorkspaceContext — init(project) / add_file / mark_task_completed /
  add_artifact / snapshot(project_dir) / save(project_dir, ctx) /
  load(project_dir) (失败安全: 缺文件 → 空 context) + acquire_reservation /
  release_reservation / reserved_files

设计: docs/sprint10/S10-056-team-design.md §2.5 / §4;
docs/sprint10/S10-059-team-decision-design.md §3 (P2)
边界:
- 纯标准库 (json/pathlib), 零模块依赖; 失败安全 (缺失/损坏 → 空 context/空锁)
- 变更方法 (add_*) 读-改-落盘-返回: 幂等追加 (文件/任务/产物去重;
  agent_history 为日志, 只追加)
- 锁粒度: 文件级; 同 Agent 重入 (同 agent 再次 acquire) → 幂等更新,
  不同 Agent → None (写权限互斥)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 上下文文件名 (project_dir/workspace_context.json — 设计 §4 资产口径)
WORKSPACE_CONTEXT_FILE_NAME = "workspace_context.json"

#: 文件锁资产文件名 (project_dir/workspace_locks.json — S10-059 P2 资产口径)
WORKSPACE_LOCKS_FILE_NAME = "workspace_locks.json"


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
        """任意结构 → 全字段上下文 (缺字段 → 空列表; 非 dict → 空上下文)。

        S10-059 P2: active_agent/active_task/reserved_files/workspace_snapshot/
        changed_files 扩展字段 — 仅当 data 中存在时注入 (失败安全缺省);
        data 无扩展字段 → 不注入 (旧式上下文精确键 roundtrip 向后兼容 —
        init 保持 5 字段, 精确键断言)。
        """
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
        # ---- S10-059 P2: Workspace Isolation 扩展字段 (仅 data 中存在时注入)
        if "active_agent" in data or "active_task" in data:
            ctx["active_agent"] = str(data.get("active_agent") or "")
            ctx["active_task"] = str(data.get("active_task") or "")
        if "reserved_files" in data:
            ctx["reserved_files"] = [
                str(f)
                for f in (data.get("reserved_files") or [])
                if not isinstance(f, dict)
            ]
        if "workspace_snapshot" in data:
            snapshot = data.get("workspace_snapshot")
            ctx["workspace_snapshot"] = (
                {str(k): v for k, v in snapshot.items()}
                if isinstance(snapshot, dict)
                else {}
            )
        if "changed_files" in data:
            ctx["changed_files"] = [
                str(f)
                for f in (data.get("changed_files") or [])
                if not isinstance(f, dict)
            ]
        return ctx

    @staticmethod
    def _ensure_isolated(ctx: dict[str, Any]) -> dict[str, Any]:
        """确保隔离扩展字段存在 (旧式 5 字段上下文 → 补全缺省值; 就地补充)。"""
        defaults = {
            "active_agent": "",
            "active_task": "",
            "reserved_files": [],
            "workspace_snapshot": {},
            "changed_files": [],
        }
        for key, default in defaults.items():
            ctx.setdefault(key, default)
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
        """当前上下文深拷贝 (改返回值不影响落盘状态; 含 dict 字段深拷贝)。"""
        ctx = cls.load(project_dir)
        return {k: cls._copy(v) for k, v in ctx.items()}

    @staticmethod
    def _copy(value: Any) -> Any:
        """递归深拷贝 (list/dict 内嵌 dict — workspace_snapshot 支持)。"""
        if isinstance(value, dict):
            return {k: WorkspaceContext._copy(v) for k, v in value.items()}
        if isinstance(value, list):
            return [WorkspaceContext._copy(v) for v in value]
        return value

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

    # ------------------------------------------------------------ S10-059 P2: Reservation

    @classmethod
    def _locks_file(cls, project_dir: Any) -> Path:
        """文件锁资产路径 (project_dir/workspace_locks.json)。"""
        return Path(project_dir) / WORKSPACE_LOCKS_FILE_NAME

    @classmethod
    def _load_locks(cls, project_dir: Any) -> dict[str, dict[str, Any]]:
        """读 workspace_locks.json → {file: {agent, task_id, acquired_at}};
        缺失/损坏 → {} (失败安全)。"""
        path = cls._locks_file(project_dir)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空锁
            return {}
        if not isinstance(data, dict):
            return {}
        locks: dict[str, dict[str, Any]] = {}
        for file, holder in data.items():
            if isinstance(holder, dict):
                locks[str(file)] = {
                    "agent": str(holder.get("agent") or ""),
                    "task_id": str(holder.get("task_id") or ""),
                    "acquired_at": str(holder.get("acquired_at") or ""),
                }
        return locks

    @classmethod
    def _save_locks(cls, project_dir: Any, locks: dict[str, dict[str, Any]]) -> Path:
        """落盘 workspace_locks.json (父目录自动创建; 中文可读)。"""
        path = cls._locks_file(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(locks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    @classmethod
    def reserved_files(cls, project_dir: Any) -> dict[str, dict[str, Any]]:
        """当前文件锁快照 {file: {agent, task_id, acquired_at}} (拷贝, 不泄漏内部)。"""
        return {f: dict(h) for f, h in cls._load_locks(project_dir).items()}

    @classmethod
    def acquire_reservation(
        cls, project_dir: Any, agent: Any, task_id: Any, files: list[str]
    ) -> Optional[dict[str, Any]]:
        """文件写权限锁定 (S10-059 P2): 成功 → {agent, task_id, files,
        acquired_at} + 上下文 active_agent/active_task/reserved_files/
        workspace_snapshot 更新; 同文件已被其他 agent 占 → None (BLOCK 信号)。

        核心: 同一文件不能被两个 Agent 同时拥有写权限 — 文件级互斥;
        同 Agent 重入 (同 agent 再次 acquire) → 幂等更新, 不视为冲突。
        """
        agent_s = str(agent or "")
        task_id_s = str(task_id or "")
        files_norm = [
            str(f) for f in (files or []) if f is not None and not isinstance(f, dict)
        ]
        now = datetime.now(timezone.utc).isoformat()
        locks = cls._load_locks(project_dir)
        for file in files_norm:
            holder = locks.get(file)
            if holder and str(holder.get("agent") or "") != agent_s:
                # 同文件已被其他 agent 占用 → 冲突 (BLOCK 信号)
                return None
        for file in files_norm:
            locks[file] = {"agent": agent_s, "task_id": task_id_s, "acquired_at": now}
        if files_norm:
            cls._save_locks(project_dir, locks)
            # 上下文: active_agent/active_task/reserved_files/workspace_snapshot
            ctx = cls._ensure_isolated(cls.load(project_dir))
            ctx["active_agent"] = agent_s
            ctx["active_task"] = task_id_s
            for file in files_norm:
                if file not in ctx["reserved_files"]:
                    ctx["reserved_files"].append(file)
            # workspace_snapshot: 获取锁时刻的工作区快照 (决策上下文资产)
            ctx["workspace_snapshot"] = cls.snapshot(project_dir)
            cls.save(project_dir, ctx)
        return {"agent": agent_s, "task_id": task_id_s, "files": files_norm, "acquired_at": now}

    @classmethod
    def release_reservation(cls, project_dir: Any, agent: Any, task_id: Any) -> None:
        """释放该任务持有的文件锁 (S10-059 P2): 移除锁 + changed_files 记录
        (释放即变更 — 资产化) + active_agent/active_task/reserved_files 清理。

        只释放 (agent, task_id) 自己的锁; 无锁 → 无操作 (失败安全)。
        """
        agent_s = str(agent or "")
        task_id_s = str(task_id or "")
        locks = cls._load_locks(project_dir)
        released = [
            file
            for file, holder in locks.items()
            if str(holder.get("task_id") or "") == task_id_s
            and str(holder.get("agent") or "") == agent_s
        ]
        if not released:
            return
        for file in released:
            del locks[file]
        cls._save_locks(project_dir, locks)
        ctx = cls._ensure_isolated(cls.load(project_dir))
        for file in released:
            if file not in ctx["changed_files"]:
                ctx["changed_files"].append(file)
        if ctx.get("active_task") == task_id_s:
            ctx["active_task"] = ""
            ctx["active_agent"] = ""
            ctx["reserved_files"] = [
                f for f in ctx["reserved_files"] if f not in released
            ]
        cls.save(project_dir, ctx)
