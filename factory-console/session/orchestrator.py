"""factory-console/session/orchestrator.py — Autonomous Production Loop 执行编排 (S10-052 P0-P6)。

读取 execution_plan.json → 任务队列 (顺序执行) → 状态持久化 (execution_state.json)
→ 失败处理 (retry/max_retry, 不无限重试) → Lifecycle 自动推进
(EXECUTION_READY → DEVELOPMENT → TESTING → DELIVERED) → ExecutionResult 汇总。

设计: docs/sprint10/S10-052-production-loop-design.md §2-§7

组件:
- ExecutionResult  — 执行结果汇总 (project/status/completed/failed/artifacts/duration/cost/errors)
- ExecutionState   — 任务状态持久化 (load/save/from_dict/to_dict, execution_state.json)
- ExecutionOrchestrator — 编排器: execute_project (全新执行) / get_progress (只读查询)
  / resume (从 state 继续 pending/failed)

复用边界 (验收 H):
- 任务执行 = execute_fn 注入 (缺省 _default_execute_fn 薄调 actions.execute_task,
  S10-049 复用 Agent Runtime; 测试注入 mock, 零真实 LLM/网络)
- 本模块不重实现 Agent Runtime, 不调 LLM, 不引入新依赖 (纯标准库)
- 不 import .actions 于模块顶层 (避免循环依赖 — actions.py 顶层 import 本模块);
  桥接函数内惰性 import (同 pipeline.AgentAssignment 惰性注入模式)
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .intent import IntentObject
from .pipeline import Lifecycle
from .quality import RepairManager, ValidationResult, Validator


class ProjectNotFoundError(Exception):
    """项目未找到 (slug/name 均未匹配 projects/ 下目录) — 明确报错, 不静默。"""


class PlanNotFoundError(Exception):
    """execution_plan.json 缺失 — 项目未准备工程 (prepare_project 未执行)。"""


class ExecutionStateError(Exception):
    """execution_state.json 缺失/损坏 — resume/get_progress 无法读取。"""


#: 任务执行函数契约: (task: dict, project_dir: Path, workspace: Path) -> dict
#: 返回 {success: bool, artifact?: str, error?: str, cost?: str}
ExecuteFn = Callable[[dict[str, Any], Path, Path], dict[str, Any]]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """落盘 JSON (ensure_ascii=False — 中文可读; 父目录自动创建)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _read_json(path: Path) -> dict[str, Any]:
    """读取 JSON (失败 → 抛, 由调用方失败安全处理)。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _default_execute_fn(
    task: dict[str, Any], project_dir: Path, workspace: Path
) -> dict[str, Any]:
    """缺省任务执行桥 (验收 H): 薄调 actions.execute_task, 复用 Agent Runtime。

    构造 execute_task intent {objective: task.name, task_id, agent_id: task.agent,
    project: 项目目录} → ExecutionContext → actions.execute_task
    (S10-049: 薄调 exec.cli.cmd_exec_run) → 归一化执行结果 dict。

    惰性 import .actions (顶层循环依赖护栏: actions.py 顶层 import 本模块)。
    """
    from .action import ExecutionContext
    from .actions import execute_task
    from .context import SessionContext

    intent = IntentObject(
        intent_type="execute_task",
        params={
            "objective": str(task.get("name") or task.get("id") or ""),
            "task_id": str(task.get("id") or ""),
            "agent_id": str(task.get("agent") or ""),
            "project": str(project_dir),
        },
        raw=str(task.get("name") or ""),
        source="orchestrator",
    )
    ctx = ExecutionContext(
        workspace=workspace,
        session=SessionContext(workspace=str(workspace)),
        user="user",
        project=str(project_dir),
        intent=intent,
    )
    result = execute_task(ctx)
    data = result.data if isinstance(result.data, dict) else {}
    execution = data.get("execution") or {}
    if not isinstance(execution, dict):
        execution = {}
    return {
        "success": result.ok,
        "artifact": str(execution.get("artifact") or ""),
        "error": result.error,
        "cost": str(execution.get("cost") or ""),
    }


@dataclass
class ExecutionResult:
    """执行结果汇总 (设计 §3): project/status/completed/failed/artifacts/duration/cost/errors。

    status: "delivered" (全部任务完成) | "failed" (存在失败任务, 可 resume) —
    与 state.status 区分: 失败时 state.status/lifecycle 保持 development (设计 §6)。
    """

    project: str
    status: str = Lifecycle.DEVELOPMENT
    completed_tasks: int = 0
    failed_tasks: int = 0
    artifacts: list[str] = field(default_factory=list)
    duration: float = 0.0
    cost: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """渲染/审计视图 (Action data 键提升)。"""
        return {
            "project": self.project,
            "status": self.status,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "artifacts": list(self.artifacts),
            "duration": self.duration,
            "cost": self.cost,
            "errors": list(self.errors),
        }


@dataclass
class ExecutionState:
    """任务执行状态 (设计 §4): execution_state.json 内容模型。

    tasks: [{id, name, agent, status: pending/running/completed/failed,
            artifact, retry_count, error}] — status 落盘小写 (同 Lifecycle 口径)。
    """

    project: str
    status: str = Lifecycle.DEVELOPMENT
    lifecycle: Optional[str] = Lifecycle.DEVELOPMENT
    started_at: str = ""
    tasks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘/审计视图)。"""
        return {
            "project": self.project,
            "status": self.status,
            "lifecycle": self.lifecycle,
            "started_at": self.started_at,
            "tasks": list(self.tasks),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionState":
        """dict → ExecutionState (未知键忽略, 缺失字段用默认值 — 前向兼容)。"""
        return cls(
            project=str(data.get("project") or ""),
            status=str(data.get("status") or Lifecycle.DEVELOPMENT),
            lifecycle=data.get("lifecycle") or Lifecycle.DEVELOPMENT,
            started_at=str(data.get("started_at") or ""),
            tasks=list(data.get("tasks") or []),
        )

    def save(self, path: Path) -> None:
        """持久化到 path (execution_state.json; 父目录自动创建, 中文可读)。"""
        _write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: Path) -> Optional["ExecutionState"]:
        """从 path 读取; 文件缺失 → None; JSON 损坏 → 抛 ExecutionStateError。"""
        path = Path(path)
        if not path.is_file():
            return None
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001 — 损坏状态 → 明确错误, 不静默
            raise ExecutionStateError(f"execution_state.json 损坏: {exc}") from exc


class ExecutionOrchestrator:
    """Autonomous Production Loop 编排器 (设计 §2/§3)。

    execute_project: 读 execution_plan.json → 初始化 state (全 pending) → save
    → Lifecycle DEVELOPMENT → 顺序执行任务队列 (每任务状态持久化) → 汇总 →
    Lifecycle 推进 (无 failed → TESTING → DELIVERED; 有 failed → 保持 DEVELOPMENT)。
    get_progress: 只读进度查询 (不执行任何任务)。
    resume: 从 execution_state.json 继续 pending/failed 任务 (跳过 completed)。
    """

    #: 任务队列最大重试次数 (设计 §5/§7: 失败 → retry 1 次 → failed, 不无限重试)
    DEFAULT_MAX_RETRY = 1

    def __init__(
        self, workspace: Path, validator: Optional[Validator] = None
    ) -> None:
        self.workspace = Path(workspace)
        # S10-053 P2: 质量门验证器 (缺省 mock Validator; 测试注入自定义 validator)
        self.validator = validator if validator is not None else Validator()

    # ------------------------------------------------------------ 定位/加载

    def _projects_root(self) -> Path:
        return self.workspace / "projects"

    def _locate_project(self, project_id: str) -> tuple[Path, str]:
        """按 slug/name 定位项目目录 (设计 §2: projects/<slug>/)。返回 (project_dir, slug)。

        ① project_id 直接作为 slug 目录; ② 按 project.json name 扫描;
        未找到 → ProjectNotFoundError (明确, 不静默)。
        """
        projects_root = self._projects_root()
        if not projects_root.is_dir():
            raise ProjectNotFoundError(project_id)
        slug = str(project_id or "").strip().strip("/")
        if slug:
            pdir = projects_root / slug
            if pdir.is_dir():
                return pdir, slug
        # 按 name 扫描 (中文产品名 / 非 slug 引用)
        for pdir in sorted(projects_root.iterdir()):
            if not pdir.is_dir():
                continue
            meta = pdir / "project.json"
            if not meta.is_file():
                continue
            try:
                data = _read_json(meta)
            except Exception:  # noqa: BLE001 — 损坏文件跳过 (失败安全)
                continue
            if data.get("name") == project_id:
                return pdir, pdir.name
        raise ProjectNotFoundError(project_id)

    def _load_plan(self, project_dir: Path) -> dict[str, Any]:
        """读取 execution_plan.json (结构: {"tasks": [{id, name, agent_type, agent}], "count"})。

        缺失/损坏 → PlanNotFoundError (项目未准备工程 — 先执行 prepare_project)。
        """
        plan_path = project_dir / "execution_plan.json"
        if not plan_path.is_file():
            raise PlanNotFoundError(
                f"execution_plan.json 缺失: {plan_path} (请先执行 prepare_project)"
            )
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — 损坏 → 明确错误
            raise PlanNotFoundError(f"execution_plan.json 损坏: {exc}") from exc
        if not isinstance(plan, dict) or not plan.get("tasks"):
            raise PlanNotFoundError(f"execution_plan.json 无任务: {plan_path}")
        return plan

    def _state_file(self, project_dir: Path) -> Path:
        """execution_state.json 路径 (projects/<slug>/execution_state.json)。"""
        return project_dir / "execution_state.json"

    def _load_state(self, project_dir: Path) -> Optional[ExecutionState]:
        """读取 state; 缺失 → None; 损坏 → 抛 ExecutionStateError。"""
        return ExecutionState.load(self._state_file(project_dir))

    def _save_state(self, project_dir: Path, state: ExecutionState) -> None:
        """持久化 state (每任务状态变更后调用 — 可恢复)。"""
        state.save(self._state_file(project_dir))

    def _set_lifecycle(self, project_dir: Path, slug: str, status: str) -> None:
        """Lifecycle 落盘: 更新 project.json + product.json 的 status (保留既有字段)。

        缺省字段兜底 (project.json 缺失 → 新建; product.json 缺失 → 跳过 —
        orchestrator 不依赖产品资产存在)。
        """
        project_file = project_dir / "project.json"
        existing = _read_json(project_file) if project_file.is_file() else {}
        _write_json(
            project_file,
            {**existing, "name": existing.get("name") or slug, "status": status},
        )
        product_file = project_dir / "product.json"
        if product_file.is_file():
            existing_p = _read_json(product_file)
            _write_json(product_file, {**existing_p, "status": status})

    # ------------------------------------------------------------ 执行

    @staticmethod
    def _task_record(plan_task: dict[str, Any]) -> dict[str, Any]:
        """plan 任务 → state 任务记录 (初始 pending; 含 agent_type 冗余字段)。"""
        return {
            "id": str(plan_task.get("id") or ""),
            "name": str(plan_task.get("name") or plan_task.get("id") or ""),
            "agent_type": plan_task.get("agent_type"),
            "agent": str(plan_task.get("agent") or ""),
            "status": "pending",
            "artifact": "",
            "retry_count": 0,
            "error": None,
        }

    def execute_project(
        self,
        project_id: str,
        *,
        execute_fn: Optional[ExecuteFn] = None,
        max_retry: int = DEFAULT_MAX_RETRY,
    ) -> ExecutionResult:
        """全新执行 (设计 §3): 读 execution_plan.json → 初始化 state → 顺序执行。

        每任务: pending → running → completed/failed (状态逐任务持久化, 可恢复);
        失败: retry_count+1, 最多重试 max_retry 次, 仍失败 → failed (继续下一任务);
        全部完成 → Lifecycle TESTING → (测试门占位通过) → DELIVERED。
        """
        project_dir, slug = self._locate_project(project_id)
        plan = self._load_plan(project_dir)
        state = ExecutionState(
            project=slug,
            status=Lifecycle.DEVELOPMENT,
            lifecycle=Lifecycle.DEVELOPMENT,
            started_at=datetime.now(timezone.utc).isoformat(),
            tasks=[self._task_record(t) for t in plan.get("tasks") or []],
        )
        self._save_state(project_dir, state)
        # Lifecycle: EXECUTION_READY → DEVELOPMENT (project.json/product.json status)
        self._set_lifecycle(project_dir, slug, Lifecycle.DEVELOPMENT)
        started = time.monotonic()
        result = self._run_queue(
            project_dir, slug, state, execute_fn=execute_fn, max_retry=max_retry
        )
        result.duration = time.monotonic() - started
        return result

    def resume(
        self,
        project_id: str,
        *,
        execute_fn: Optional[ExecuteFn] = None,
        max_retry: int = DEFAULT_MAX_RETRY,
    ) -> ExecutionResult:
        """恢复执行 (设计 §3): 从 execution_state.json 继续 pending/failed 任务。

        跳过 completed; failed 任务重置 retry_count 重新执行 (仍受 max_retry 约束);
        无待恢复任务 → 直接汇总 (不重跑)。
        """
        project_dir, slug = self._locate_project(project_id)
        state = self._load_state(project_dir)
        if state is None:
            raise ExecutionStateError(
                f"execution_state.json 缺失: {self._state_file(project_dir)} (请先 execute_project)"
            )
        state.status = Lifecycle.DEVELOPMENT
        state.lifecycle = Lifecycle.DEVELOPMENT
        for task in state.tasks:
            if task.get("status") == "failed":
                task["status"] = "pending"
                task["retry_count"] = 0
                task["error"] = None
        self._save_state(project_dir, state)
        started = time.monotonic()
        result = self._run_queue(
            project_dir, slug, state, execute_fn=execute_fn, max_retry=max_retry
        )
        result.duration = time.monotonic() - started
        return result

    def needs_resume(self, project_id: str) -> bool:
        """是否存在待恢复任务 (state 存在且含 pending/failed) — Action 分派用。

        失败安全: 定位失败/state 缺失/损坏 → False (走全新 execute_project)。
        """
        try:
            project_dir, _ = self._locate_project(project_id)
            state = self._load_state(project_dir)
        except Exception:  # noqa: BLE001 — 失败安全: 无法判定 → 不恢复
            return False
        if state is None:
            return False
        return any(t.get("status") in ("pending", "failed") for t in state.tasks)

    def get_progress(self, project_id: str) -> dict[str, Any]:
        """进度查询 (设计 §3, 验收 F): 只读 execution_state.json, 不执行任何任务。

        返回 {project, status, lifecycle, tasks_total, completed, running,
        pending, failed, agents} + S10-053 增强 (验收 H): validation
        {passed, failed, not_run} + repair {pending, done, failed}
        (repair 计数来自 repair_task.json 只读)。state 缺失 → status="not_started" 零值。
        """
        project_dir, slug = self._locate_project(project_id)
        state = self._load_state(project_dir)
        base: dict[str, Any] = {
            "project": slug,
            "status": "not_started",
            "lifecycle": None,
            "tasks_total": 0,
            "completed": 0,
            "running": 0,
            "pending": 0,
            "failed": 0,
            "agents": [],
            "validation": {"passed": 0, "failed": 0, "not_run": 0},
            "repair": {"pending": 0, "done": 0, "failed": 0},
        }
        if state is None:
            return base
        counts = Counter(str(t.get("status")) for t in state.tasks)
        agents = sorted(
            {
                str(t.get("agent"))
                for t in state.tasks
                if t.get("agent") and str(t.get("agent")) != "None"
            }
        )
        val_passed = sum(1 for t in state.tasks if t.get("validation") == "passed")
        val_failed = sum(1 for t in state.tasks if t.get("validation") == "failed")
        repairs = RepairManager.load_repairs(project_dir)
        return {
            "project": state.project or slug,
            "status": state.status,
            "lifecycle": state.lifecycle,
            "tasks_total": len(state.tasks),
            "completed": counts.get("completed", 0),
            "running": counts.get("running", 0),
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
            "agents": agents,
            "validation": {
                "passed": val_passed,
                "failed": val_failed,
                "not_run": len(state.tasks) - val_passed - val_failed,
            },
            "repair": {
                "pending": sum(1 for r in repairs if r.get("status") == "pending"),
                "done": sum(1 for r in repairs if r.get("status") == "completed"),
                "failed": sum(1 for r in repairs if r.get("status") == "failed"),
            },
        }

    # ------------------------------------------------------------ 任务队列

    def _run_queue(
        self,
        project_dir: Path,
        slug: str,
        state: ExecutionState,
        *,
        execute_fn: Optional[ExecuteFn],
        max_retry: int,
    ) -> ExecutionResult:
        """任务队列 (设计 §5 + S10-053 §8): 顺序执行, 逐任务持久化 + 质量门。

        顺序执行 (未来 DAG: 保留 TaskQueue.next_pending/mark_done 语义扩展点 —
        本版 state.tasks 顺序即队列顺序)。完成统计 + Lifecycle 推进 (§6)。

        S10-053 P2 质量门 (设计 §8): 每任务 outcome 后 → validator.validate:
        - success → task completed (state.tasks[].validation="passed")
        - fail (执行失败或验证失败) → task failed + RepairManager.create_repair
          (repair_task.json, 由 repair_task Action / resume 处理)
        全部完成且无验证失败 → TESTING → VALIDATION_PASS → DELIVERED;
        有失败 → 保持 DEVELOPMENT (可 repair/resume)。验证汇总 →
        validation_result.json 落盘 (验收 I)。
        """
        runner: ExecuteFn = execute_fn if execute_fn is not None else _default_execute_fn
        completed = failed = 0
        artifacts: list[str] = []
        errors: list[str] = []
        costs: list[str] = []
        validations: list[ValidationResult] = []
        for task in state.tasks:
            if task.get("status") == "completed":
                # 已完成任务跳过 (resume 语义: 不重跑); 缺 validation 字段 → 默认 passed
                task.setdefault("validation", "passed")
                completed += 1
                if task.get("artifact"):
                    artifacts.append(str(task["artifact"]))
                continue
            outcome = self._execute_with_retry(
                project_dir, state, task, runner, max_retry
            )
            # S10-053: Validation Gate — 每任务 outcome 后验证 (设计 §8)
            validation = self.validator.validate(task, outcome)
            task["validation"] = "passed" if validation.success else "failed"
            validations.append(validation)
            self._save_state(project_dir, state)
            if task.get("status") == "completed" and validation.success:
                completed += 1
                if task.get("artifact"):
                    artifacts.append(str(task["artifact"]))
            else:
                failed += 1
                if task.get("status") == "completed":
                    # 执行成功但验证失败 → 同样视为失败 (质量门: 无 success 禁止交付)
                    task["status"] = "failed"
                    task["error"] = "; ".join(validation.errors) or "验证失败"
                    self._save_state(project_dir, state)
                reason = str(
                    task.get("error")
                    or "; ".join(validation.errors)
                    or "任务执行失败"
                )
                errors.append(f"{task.get('id') or task.get('name')}: {reason}")
                # S10-053: 失败 → repair_task.json (待修复队列, 不无限循环由 max_retry 约束)
                RepairManager.create_repair(
                    project_dir,
                    task,
                    reason,
                    retry_count=int(task.get("retry_count") or 0),
                )
            if isinstance(outcome, dict) and outcome.get("cost"):
                costs.append(str(outcome["cost"]))
        result = ExecutionResult(
            project=slug,
            status=Lifecycle.DELIVERED if failed == 0 else "failed",
            completed_tasks=completed,
            failed_tasks=failed,
            artifacts=artifacts,
            cost=" · ".join(costs),
            errors=errors,
        )
        # Lifecycle 推进 (§6 + S10-053 §4): 无 failed (含全部验证通过) →
        # TESTING → VALIDATION_PASS → DELIVERED; 有 failed → 保持 DEVELOPMENT
        if failed == 0:
            state.status = Lifecycle.TESTING
            state.lifecycle = Lifecycle.TESTING
            self._save_state(project_dir, state)
            self._set_lifecycle(project_dir, slug, Lifecycle.TESTING)
            state.status = Lifecycle.VALIDATION_PASS
            state.lifecycle = Lifecycle.VALIDATION_PASS
            self._save_state(project_dir, state)
            self._set_lifecycle(project_dir, slug, Lifecycle.VALIDATION_PASS)
            state.status = Lifecycle.DELIVERED
            state.lifecycle = Lifecycle.DELIVERED
            self._save_state(project_dir, state)
            self._set_lifecycle(project_dir, slug, Lifecycle.DELIVERED)
        else:
            state.status = Lifecycle.DEVELOPMENT
            state.lifecycle = Lifecycle.DEVELOPMENT
            self._save_state(project_dir, state)
        # S10-053: 验证结果资产化 — validation_result.json 落盘 (验收 I)
        summary = ValidationResult(
            success=failed == 0,
            tests_total=len(validations),
            tests_passed=sum(1 for v in validations if v.success),
            tests_failed=sum(1 for v in validations if not v.success),
            errors=[
                f"{task.get('id') or task.get('name')}: {err}"
                for task, v in zip(state.tasks, validations)
                for err in (v.errors if not v.success else [])
            ],
        )
        self.validator.save(project_dir, slug, summary)
        return result

    def _execute_with_retry(
        self,
        project_dir: Path,
        state: ExecutionState,
        task: dict[str, Any],
        runner: ExecuteFn,
        max_retry: int,
    ) -> dict[str, Any]:
        """单任务执行 + 失败重试 (设计 §7): pending → running → completed/failed。

        失败: retry_count+1; retry_count <= max_retry → 重试一次; 仍失败 →
        status=failed + error (不无限重试, 继续下一任务)。每次状态变更即持久化。
        runner 异常 → 视为失败 (失败安全, 不裸抛)。
        """
        retries = 0
        while True:
            task["status"] = "running"
            task["error"] = None
            self._save_state(project_dir, state)
            try:
                outcome = runner(task, project_dir, self.workspace) or {}
            except Exception as exc:  # noqa: BLE001 — 失败安全: 异常 → 失败
                outcome = {"success": False, "error": str(exc)}
            if not isinstance(outcome, dict):
                outcome = {"success": False, "error": "execute_fn 返回非 dict"}
            if outcome.get("success"):
                task["status"] = "completed"
                task["artifact"] = str(outcome.get("artifact") or "")
                task["retry_count"] = retries
                task["error"] = None
                self._save_state(project_dir, state)
                return outcome
            task["error"] = str(outcome.get("error") or "任务执行失败")
            if retries < max_retry:
                retries += 1
                task["retry_count"] = retries
                continue  # 重试 (最多 max_retry 次 — 不无限重试)
            task["status"] = "failed"
            task["retry_count"] = retries
            self._save_state(project_dir, state)
            return outcome
