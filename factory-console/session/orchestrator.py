"""factory-console/session/orchestrator.py — Autonomous Production Loop 执行编排 (S10-052 P0-P6)。

读取 execution_plan.json → 任务队列 (顺序执行) → 状态持久化 (execution_state.json)
→ 失败处理 (retry/max_retry, 不无限重试) → Lifecycle 自动推进
(EXECUTION_READY → DEVELOPMENT → TESTING → DELIVERED) → ExecutionResult 汇总。

S10-057 (Team Production Validation, team mode 增强): ConflictResolver 计划级
冲突解决 (conflict_resolution.json) + TeamExecutionState (team_execution_state.json,
pause/resume/progress) + Agent Handoff (handoff_messages.json) + Workspace Context
注入 (task["context"] 透传) + Team Validation (QA Review + pytest 命令门) +
team_report.md 生成。solo mode 行为零变化 (team_run 不传 → 原路径)。

设计: docs/sprint10/S10-052-production-loop-design.md §2-§7;
docs/sprint10/S10-056-team-design.md §3 TeamExecutionMode;
docs/sprint10/S10-057-team-production-design.md §P0-§P5

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

from .agents import AgentMatcher, AgentMetrics, AgentRegistry
from .conflicts import (
    ConflictDetector,
    ConflictRecord,
    ConflictResolver,
    FileOwnership,
)
from .dependencies import TaskDependencyGraph
from .intent import IntentObject
from .messages import AgentMessageStore, HandoffStore
from .pipeline import Lifecycle
from .quality import RepairManager, ValidationResult, Validator
from .roles import RoleSystem
from .team_state import TeamExecutionState
from .teams import DEFAULT_TEAM_ID, TeamRegistry
from .workspace import WorkspaceContext


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
        # S10-055 Task 004: Agent 选择理由透传 (execution_plan.json reason →
        # 执行结果; 旧式 plan 无 reason → 空串, 失败安全)
        "reason": str(task.get("reason") or ""),
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


@dataclass
class TeamRunContext:
    """团队执行钩子 (S10-056 批次 B + S10-057): 冲突检测/解决 + Workspace 注入 +
    Handoff + TeamState 更新。

    仅 team mode 使用 (solo mode 无此上下文, 行为零变化):
    - before_task: ConflictDetector.detect — 同文件多任务 → ConflictRecord
      (记录不阻塞 — 冲突不中断执行, 边界 §7 只检测不解决)
    - inject_context: 任务执行前 WorkspaceContext 快照 (completed_tasks/artifacts/
      messages/decisions) → task["context"] 透传 (设计 §P3 — execute_fn 可读)
    - after_task: 任务成功 → WorkspaceContext.mark_task_completed/add_artifact
      (让 Agent 知道之前谁做过什么 — 设计 §2.5) + AgentMessage 可选记录
      (architect → 成员 指令型消息 — 设计 §2.6, 接口预留, 缺省关闭)
    - S10-057 增强: handoff_after_task — 前序任务完成 → HandoffStore 交接给
      后继任务 (requirement/decision/constraints → handoff_messages.json, §P2);
      update_team_state — TeamExecutionState 每任务状态写入 (§P1)
    """

    team: dict[str, Any]
    detector: ConflictDetector
    store: Optional[AgentMessageStore] = None
    messages_from: str = "architect-agent"
    # S10-057: 后继任务映射 (依赖图推导: task_id → [依赖它的任务]) + 任务索引
    successors: dict[str, list[str]] = field(default_factory=dict)
    tasks_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    handoff_store: Optional[HandoffStore] = None

    def before_task(
        self, project_dir: Path, task: dict[str, Any]
    ) -> list[ConflictRecord]:
        """任务执行前冲突检测 (同文件已被其他 task 归属 → ConflictRecord, 记录不阻塞)。"""
        files = [str(f) for f in (task.get("files") or []) if not isinstance(f, dict)]
        return self.detector.detect(project_dir, str(task.get("id") or ""), files)

    def inject_context(self, project_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
        """Workspace Context 注入 (设计 §P3): workspace_context.json 快照 +
        消息/交接 → task["context"] 透传 (execute_fn 可读)。

        上下文: {project, completed_tasks, artifacts, messages, decisions} —
        messages 来自 AgentMessageStore (可选), decisions 为发给该任务的交接
        (handoff_messages.json, to == task.agent)。只读组装, 不改 workspace。
        """
        ctx = WorkspaceContext.load(project_dir)
        messages = (
            self.store.list() if self.store is not None else []
        )
        decisions: list[dict[str, Any]] = []
        if self.handoff_store is not None:
            agent = str(task.get("agent") or "")
            decisions = [
                dict(h)
                for h in self.handoff_store.list()
                if agent and str(h.get("to")) == agent
            ]
        context = {
            "project": str(ctx.get("project") or Path(project_dir).name),
            "completed_tasks": list(ctx.get("completed_tasks") or []),
            "artifacts": list(ctx.get("artifacts") or []),
            "messages": [dict(m) for m in messages],
            "decisions": decisions,
        }
        task["context"] = context
        return context

    def after_task(self, project_dir: Path, task: dict[str, Any]) -> None:
        """任务成功后 Workspace 更新 + 可选消息 (仅 completed 任务)。"""
        if str(task.get("status")) != "completed":
            return
        WorkspaceContext.mark_task_completed(
            project_dir,
            str(task.get("id") or ""),
            str(task.get("agent") or ""),
            "success",
        )
        artifact = task.get("artifact")
        if artifact:
            WorkspaceContext.add_artifact(project_dir, str(artifact))
        if self.store is not None:
            self.store.send(
                self.messages_from,
                str(task.get("agent") or ""),
                "instruction",
                f"Task {task.get('id') or ''} completed: {task.get('name') or ''}",
            )

    def handoff_after_task(self, project_dir: Path, task: dict[str, Any]) -> None:
        """Agent Handoff (设计 §P2): 前序任务完成 → 后继任务交接。

        依赖关系 → 后继任务 (successors); 交接内容: requirement (后继任务
        requirement/name), decision (前序完成决策), constraints (后继任务
        constraints/缺省) → handoff_messages.json。无后继/无 store → 无操作。
        """
        if self.handoff_store is None:
            return
        task_id = str(task.get("id") or "")
        succ_ids = list(self.successors.get(task_id) or [])
        if not succ_ids:
            return
        from_agent = str(task.get("agent") or "") or self.messages_from
        for succ_id in succ_ids:
            succ = self.tasks_by_id.get(succ_id) or {}
            to_agent = str(succ.get("agent") or "") or self.messages_from
            self.handoff_store.send(
                from_agent,
                to_agent,
                requirement=str(
                    succ.get("requirement") or succ.get("name") or succ_id
                ),
                decision=f"{task_id} 完成: {task.get('name') or task_id}",
                constraints=str(
                    succ.get("constraints") or "遵循前序设计与 workspace 上下文"
                ),
                task_id=succ_id,
            )

    @staticmethod
    def update_team_state(
        project_dir: Path, task: dict[str, Any], status: str
    ) -> None:
        """TeamExecutionState 每任务状态写入 (设计 §P1): team_execution_state.json。"""
        TeamExecutionState.update(
            project_dir,
            str(task.get("id") or ""),
            status,
            agent=str(task.get("agent") or ""),
            artifact=str(task.get("artifact") or "") if status == "completed" else None,
        )

    @staticmethod
    def is_paused(project_dir: Path) -> bool:
        """团队是否暂停 (team_execution_state.json status == paused)。"""
        return TeamExecutionState.is_paused(project_dir)


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
            # S10-056: 空任务 plan → 返回空计划 (空执行, 不报错 — 团队拓扑/空项目可恢复)
            if isinstance(plan, dict) and "tasks" in plan:
                return plan
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
        """plan 任务 → state 任务记录 (初始 pending; 含 agent_type/feature 冗余字段)。

        S10-055 Task 004: feature/epic 归属透传 (Feature Level Execution —
        get_feature_progress 按 task.feature 分组); 旧式 plan 无此字段 → 兼容缺失。
        S10-056 批次 B: required_role (团队角色分配 — AgentMatcher 匹配结果透传)
        + files (冲突检测输入 — ConflictDetector 消费), 缺省 None/[] 兼容旧式 plan。
        """
        return {
            "id": str(plan_task.get("id") or ""),
            "name": str(plan_task.get("name") or plan_task.get("id") or ""),
            "agent_type": plan_task.get("agent_type"),
            "agent": str(plan_task.get("agent") or ""),
            "feature": plan_task.get("feature"),
            "epic": plan_task.get("epic"),
            "reason": plan_task.get("reason"),  # S10-055: Agent 选择理由透传 (可解释调度)
            "required_role": plan_task.get("required_role"),  # S10-056: 团队角色
            "matched_role": plan_task.get("matched_role"),  # S10-056: 角色匹配结果 (审计)
            "files": [
                str(f) for f in (plan_task.get("files") or []) if not isinstance(f, dict)
            ],  # S10-056: 冲突检测输入
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
        mode: str = "solo",
        team_id: str = DEFAULT_TEAM_ID,
        teams_file: Optional[Path] = None,
        agents_file: Optional[Path] = None,
        dependencies_file: Optional[Path] = None,
        conflicts_file: Optional[Path] = None,
        messages_file: Optional[Path] = None,
        enable_messages: bool = False,
        validation_command: Optional[str] = None,
    ) -> ExecutionResult:
        """全新执行 (设计 §3): 读 execution_plan.json → 初始化 state → 顺序执行。

        mode="solo" (缺省): 原行为完全不变 — 任务按 plan 顺序执行, 无团队钩子。
        mode="team" (S10-056 批次 B, 设计 §3 TeamExecutionMode):
        ① 读 team.json (TeamRegistry.get(team_id), 缺省默认 software-team)
        ② required_role 任务 → RoleSystem.role_matches 过滤团队成员 →
           AgentMatcher 选最佳成员 (skill × 成功率 × 成本, 可解释 reason)
        ③ TaskDependencyGraph.topological_order 拓扑排序 (无依赖 → 原顺序)
        ④ 每任务: ConflictDetector.detect (同文件冲突 → ConflictRecord,
           记录不阻塞) → 执行 → WorkspaceContext 更新 (mark_task_completed/
           add_artifact) → AgentMessage 可选记录 (architect → 成员 指令接口)

        S10-057 (team mode 增强, solo 零变化):
        - ConflictResolver 计划级冲突解决 (同文件 → 重排/串行 → conflict_resolution.json)
        - TeamExecutionState 每任务状态 (team_execution_state.json, pause/resume/progress)
        - Workspace Context 注入 (task["context"] = {completed_tasks, artifacts,
          messages, decisions} — execute_fn 可读, 设计 §P3)
        - Agent Handoff (前序完成 → 后继交接 → handoff_messages.json, 设计 §P2)
        - Team Validation (全部完成 → QA Review → validation_command 命令门
          (如 "pytest"); 缺省 None → 不执行命令, 保持既有 mock 语义;
          失败 → repair 记录 + 保持 DEVELOPMENT — Repair Loop 保留)
        - team_report.md 生成 (team/tasks/agents/artifacts/validation/conflicts/handoffs)

        每任务: pending → running → completed/failed (状态逐任务持久化, 可恢复);
        失败: retry_count+1, 最多重试 max_retry 次, 仍失败 → failed (继续下一任务);
        全部完成 → Lifecycle TESTING → (测试门占位通过) → DELIVERED。
        """
        project_dir, slug = self._locate_project(project_id)
        plan = self._load_plan(project_dir)
        plan_tasks = list(plan.get("tasks") or [])
        team_run: Optional[TeamRunContext] = None
        if mode == "team":
            plan_tasks, team_run = self._team_prepare(
                project_dir,
                plan_tasks,
                team_id=team_id,
                teams_file=teams_file,
                agents_file=agents_file,
                dependencies_file=dependencies_file,
                conflicts_file=conflicts_file,
                messages_file=messages_file,
                enable_messages=enable_messages,
            )
        state = ExecutionState(
            project=slug,
            status=Lifecycle.DEVELOPMENT,
            lifecycle=Lifecycle.DEVELOPMENT,
            started_at=datetime.now(timezone.utc).isoformat(),
            tasks=[self._task_record(t) for t in plan_tasks],
        )
        self._save_state(project_dir, state)
        # Lifecycle: EXECUTION_READY → DEVELOPMENT (project.json/product.json status)
        self._set_lifecycle(project_dir, slug, Lifecycle.DEVELOPMENT)
        started = time.monotonic()
        result = self._run_queue(
            project_dir,
            slug,
            state,
            execute_fn=execute_fn,
            max_retry=max_retry,
            team_run=team_run,
            validation_command=validation_command,
        )
        result.duration = time.monotonic() - started
        return result

    def _team_prepare(
        self,
        project_dir: Path,
        plan_tasks: list[dict[str, Any]],
        *,
        team_id: str,
        teams_file: Optional[Path],
        agents_file: Optional[Path],
        dependencies_file: Optional[Path],
        conflicts_file: Optional[Path],
        messages_file: Optional[Path],
        enable_messages: bool,
    ) -> tuple[list[dict[str, Any]], TeamRunContext]:
        """团队模式准备 (S10-056 批次 B + S10-057): 角色匹配 + 依赖拓扑 + 冲突解决
        + 交接/团队状态初始化。

        ① 团队: TeamRegistry.get(team_id) 缺省 → 默认 software-team (失败安全);
        ② 角色匹配: required_role 任务 → RoleSystem.role_matches 过滤团队成员 →
           AgentMatcher 选最佳 (skill 匹配 × 成功率 × 成本); 无匹配成员
           → 保持原 assignment (失败安全, 不抛);
        ③ 拓扑排序: TaskDependencyGraph.topological_order (无依赖 → 原顺序,
           顺序执行兼容 — 设计 §2.4);
        ④ 后继映射: 依赖图 → successors {task_id: [依赖它的任务]} (Handoff 输入);
        ⑤ 冲突解决 (S10-057 §P0): ConflictResolver.detect_and_resolve — 计划级
           同文件冲突 → 策略 (dependency_delay 缺省) → ordered_tasks 重排 →
           落盘 conflict_resolution.json (projects/<slug>/);
        ⑥ TeamRunContext: 冲突检测 (detect, 记录不阻塞) + Workspace 注入 +
           可选 AgentMessage (architect → 成员 指令接口, enable_messages 开启)
           + HandoffStore (handoff_messages.json) + successors;
        ⑦ TeamExecutionState.init (S10-057 §P1): team_execution_state.json
           (team/tasks/agent/status pending)。
        返回 (排序后 plan_tasks, team_run 钩子)。
        """
        team = TeamRegistry.get(team_id, teams_file=teams_file)
        if team is None:
            team = TeamRegistry.build_default_team(agents_file=agents_file)
        registry = AgentRegistry.load(agents_file)
        member_roles = {
            str(m.get("agent")): str(m.get("role") or "")
            for m in (team.get("members") or [])
            if isinstance(m, dict) and m.get("agent")
        }
        # 团队成员注册表 (角色匹配候选 — 只从团队成员中选, 不引入非团队成员)
        member_registry = {aid: registry[aid] for aid in member_roles if aid in registry}
        records_file = self.workspace / "exec" / "execution_records.json"
        metrics = (
            AgentMetrics.load_from_records(records_file)
            if records_file.is_file()
            else {}
        )
        matcher = AgentMatcher(registry=member_registry, metrics=metrics)
        for task in plan_tasks:
            required_role = str(task.get("required_role") or "").strip()
            if not required_role:
                continue
            candidates = {
                aid: agent
                for aid, agent in member_registry.items()
                if RoleSystem.role_matches(required_role, agent)
            }
            if not candidates:
                continue
            match = matcher.match(task, registry=candidates, metrics=metrics)
            if match.get("agent"):
                task["agent"] = match["agent"]
                task["matched_role"] = required_role  # 审计: 按角色分配
                if not task.get("reason"):
                    task["reason"] = match.get("reason") or ""
        ids = [str(t.get("id") or "") for t in plan_tasks]
        graph = TaskDependencyGraph.load(dependencies_file)
        if all(ids):
            order = graph.topological_order(ids)
            pos = {tid: i for i, tid in enumerate(order)}
            plan_tasks = sorted(plan_tasks, key=lambda t: pos.get(str(t.get("id")), 0))
        # S10-057 §P2: 后继任务映射 (依赖图 → task_id → [依赖它的任务], Handoff 输入)
        tasks_by_id = {str(t.get("id") or ""): t for t in plan_tasks if t.get("id")}
        successors: dict[str, list[str]] = {}
        for task in plan_tasks:
            tid = str(task.get("id") or "")
            if not tid:
                continue
            for dep in graph.get(tid):
                if dep in tasks_by_id:
                    successors.setdefault(dep, []).append(tid)
        # S10-057 §P0: 计划级冲突预检测 + 策略解决 (同文件 → 重排/串行 →
        # conflict_resolution.json 落盘 projects/<slug>/)
        resolver = ConflictResolver(
            resolution_file=project_dir / "conflict_resolution.json"
        )
        resolution = resolver.detect_and_resolve(plan_tasks)
        if resolution.get("ordered_tasks"):
            pos = {
                tid: i for i, tid in enumerate(resolution["ordered_tasks"])
            }
            plan_tasks = sorted(plan_tasks, key=lambda t: pos.get(str(t.get("id")), 0))
            tasks_by_id = {str(t.get("id") or ""): t for t in plan_tasks if t.get("id")}
        detector = ConflictDetector(conflicts_file=conflicts_file)
        store = (
            AgentMessageStore(file=messages_file)
            if enable_messages and messages_file is not None
            else None
        )
        # S10-057 §P2: HandoffStore — handoff_messages.json (projects/<slug>/)
        handoff_store = HandoffStore(file=project_dir / "handoff_messages.json")
        # 工作区上下文初始化: 团队执行前确保 workspace_context.json 存在 (项目名落盘,
        # 设计 §2.5 让 Agent 知道共享上下文; 已存在 → 保留既有上下文, 不覆盖)
        ctx_file = project_dir / WorkspaceContext.FILE_NAME
        if not ctx_file.is_file():
            WorkspaceContext.save(project_dir, WorkspaceContext.init(project_dir.name))
        # S10-057 §P1: 团队执行状态初始化 — team_execution_state.json (全 pending)
        TeamExecutionState.init(project_dir, str(team.get("team_id") or team_id), plan_tasks)
        return plan_tasks, TeamRunContext(
            team=team,
            detector=detector,
            store=store,
            successors=successors,
            tasks_by_id=tasks_by_id,
            handoff_store=handoff_store,
        )

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
        # S10-057 §P1: 团队执行状态恢复 (暂停 → running; 无团队状态 → 无操作, 不新建)
        if (project_dir / TeamExecutionState.FILE_NAME).is_file():
            TeamExecutionState.resume(project_dir)
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

    def get_feature_progress(self, project_id: str) -> dict[str, Any]:
        """功能级进度 (S10-055 Task 004, 验收 D): 按 task.feature 分组统计。

        返回 {project, features: [{name, total_tasks, completed_tasks, status}],
        tasks_total, completed, status} — status: completed/in_progress/pending
        (ProductProgressTracker 状态推导); state 缺失 → status="not_started" +
        features=[] (失败安全)。只读, 不执行任何任务。
        """
        project_dir, slug = self._locate_project(project_id)
        state = self._load_state(project_dir)
        base: dict[str, Any] = {
            "project": slug,
            "features": [],
            "tasks_total": 0,
            "completed": 0,
            "status": "not_started",
        }
        if state is None:
            return base
        # 惰性 import .progress (progress 不依赖本模块 — 循环依赖护栏)
        from .progress import ProductProgressTracker

        doc = ProductProgressTracker.update_from_execution(state, product_name=slug)
        return {
            "project": slug,
            "features": doc["features"],
            "tasks_total": doc["tasks_total"],
            "completed": doc["tasks_completed"],
            "status": doc["status"],
        }

    def accept_project(self, project_id: str) -> bool:
        """用户验收 (S10-055 Task 005, 验收 G): USER_ACCEPTANCE → DELIVERED。

        仅 lifecycle=user_acceptance 可验收 (执行完成 + 验证通过后停在待验收);
        其它状态 (含未执行/失败/已交付) → False (明确拒绝, 不静默推进)。
        验收成功 → execution_state + project.json/product.json status=delivered。
        """
        project_dir, slug = self._locate_project(project_id)
        state = self._load_state(project_dir)
        if state is None or state.lifecycle != Lifecycle.USER_ACCEPTANCE:
            return False
        state.status = Lifecycle.DELIVERED
        state.lifecycle = Lifecycle.DELIVERED
        self._save_state(project_dir, state)
        self._set_lifecycle(project_dir, slug, Lifecycle.DELIVERED)
        return True

    # ------------------------------------------------------------ 任务队列

    def _run_queue(
        self,
        project_dir: Path,
        slug: str,
        state: ExecutionState,
        *,
        execute_fn: Optional[ExecuteFn],
        max_retry: int,
        team_run: Optional[TeamRunContext] = None,
        validation_command: Optional[str] = None,
    ) -> ExecutionResult:
        """任务队列 (设计 §5 + S10-053 §8 + S10-057): 顺序执行, 逐任务持久化 + 质量门。

        顺序执行 (未来 DAG: 保留 TaskQueue.next_pending/mark_done 语义扩展点 —
        本版 state.tasks 顺序即队列顺序; team mode 下该顺序已由
        TaskDependencyGraph.topological_order 拓扑排序 + ConflictResolver 重排决定)。

        S10-056 批次 B (team mode 钩子, solo mode 不传 → 行为零变化):
        - before_task: ConflictDetector.detect — 同文件多任务 → ConflictRecord
          (记录不阻塞, 不中断执行)
        - after_task: 任务成功 → WorkspaceContext.mark_task_completed/add_artifact
          + AgentMessage 可选记录 (architect → 成员 指令接口)

        S10-057 (team mode 增强, solo 零变化):
        - 暂停检查: 每任务迭代前 TeamExecutionState.is_paused → 停止队列
          (已完成任务保留, 剩余 pending; result.status="paused", Lifecycle 保持
          DEVELOPMENT — resume 后可继续)
        - Workspace Context 注入: inject_context — task["context"] =
          {project, completed_tasks, artifacts, messages, decisions} (设计 §P3)
        - TeamExecutionState 每任务状态: running → completed/failed (设计 §P1)
        - Handoff: after_task 后 handoff_after_task — 前序完成 → 后继交接 (§P2)
        - Team Validation (设计 §P4): 全部完成 + validation_command 提供 →
          QA Review (qa 任务全完成) + validator.validate_command (pytest 命令门);
          失败 → repair 记录 + 保持 DEVELOPMENT (Repair Loop 保留); 通过 →
          TESTING → VALIDATION_PASS → USER_ACCEPTANCE (S10-055 验收门, DELIVERED
          经 accept_project)
        - team_report.md 生成 (设计 §P5) + 团队状态终态落盘

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
        paused_stop = False  # S10-057: 团队暂停 → 停止队列 (可 resume 继续)
        for task in state.tasks:
            if task.get("status") == "completed":
                # 已完成任务跳过 (resume 语义: 不重跑); 缺 validation 字段 → 默认 passed
                task.setdefault("validation", "passed")
                completed += 1
                if task.get("artifact"):
                    artifacts.append(str(task["artifact"]))
                continue
            if team_run is not None:
                # S10-056 批次 B: 团队模式冲突检测 (同文件 → ConflictRecord, 记录不阻塞)
                team_run.before_task(project_dir, task)
                # S10-057 §P1: 暂停检查 — 已暂停 → 停止队列 (剩余任务保持 pending)
                if team_run.is_paused(project_dir):
                    paused_stop = True
                    break
                # S10-057 §P3: Workspace Context 注入 → task["context"] 透传
                team_run.inject_context(project_dir, task)
                # S10-057 §P1: TeamExecutionState 任务级 running
                team_run.update_team_state(project_dir, task, "running")
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
                if team_run is not None:
                    # S10-056 批次 B: 团队模式 Workspace 更新 + 可选消息
                    team_run.after_task(project_dir, task)
                    # S10-057 §P2: 前序完成 → 后继任务 Handoff (handoff_messages.json)
                    team_run.handoff_after_task(project_dir, task)
                    # S10-057 §P1: TeamExecutionState 任务级 completed
                    team_run.update_team_state(project_dir, task, "completed")
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
                if team_run is not None:
                    # S10-057 §P1: TeamExecutionState 任务级 failed
                    team_run.update_team_state(project_dir, task, "failed")
            if isinstance(outcome, dict) and outcome.get("cost"):
                costs.append(str(outcome["cost"]))
        # S10-057 §P4: Team Validation — 全部任务完成 (无失败/未暂停) 且显式命令门
        # (如 "pytest") → QA Review (qa 角色任务全完成, failed==0 保证) +
        # validator.validate_command 真实命令验证; 失败 → repair + 保持 DEVELOPMENT。
        team_validation: Optional[ValidationResult] = None
        if (
            team_run is not None
            and failed == 0
            and not paused_stop
            and validation_command is not None
        ):
            team_validation = self.validator.validate_command(
                project_dir, validation_command
            )
            if not team_validation.success:
                failed += 1
                err = "; ".join(team_validation.errors) or "团队验证失败 (pytest)"
                errors.append(f"team-validation: {err}")
                RepairManager.create_repair(
                    project_dir,
                    {"id": "team-validation", "name": "Team Validation (pytest)"},
                    err,
                    retry_count=0,
                )
        result = ExecutionResult(
            project=slug,
            status=(
                "paused"
                if paused_stop and failed == 0
                else (Lifecycle.USER_ACCEPTANCE if failed == 0 else "failed")
            ),
            completed_tasks=completed,
            failed_tasks=failed,
            artifacts=artifacts,
            cost=" · ".join(costs),
            errors=errors,
        )
        # Lifecycle 推进 (§6 + S10-053 §4 + S10-055 Task 005): 无 failed
        # (含全部验证通过) → TESTING → VALIDATION_PASS → USER_ACCEPTANCE (停在
        # 待验收, 不直接 DELIVERED — 验收 F); 有 failed → 保持 DEVELOPMENT;
        # 团队暂停停止 (部分完成) → 保持 DEVELOPMENT (可 resume 继续)。
        # DELIVERED 仅经 accept_project 用户确认后到达 (验收 E/G)。
        if failed == 0 and not paused_stop:
            state.status = Lifecycle.TESTING
            state.lifecycle = Lifecycle.TESTING
            self._save_state(project_dir, state)
            self._set_lifecycle(project_dir, slug, Lifecycle.TESTING)
            state.status = Lifecycle.VALIDATION_PASS
            state.lifecycle = Lifecycle.VALIDATION_PASS
            self._save_state(project_dir, state)
            self._set_lifecycle(project_dir, slug, Lifecycle.VALIDATION_PASS)
            state.status = Lifecycle.USER_ACCEPTANCE
            state.lifecycle = Lifecycle.USER_ACCEPTANCE
            self._save_state(project_dir, state)
            self._set_lifecycle(project_dir, slug, Lifecycle.USER_ACCEPTANCE)
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
        if team_run is not None:
            # S10-057 §P1: 团队状态终态落盘 (completed/paused/failed + validation 记录)
            team_state = TeamExecutionState.get(project_dir)
            team_state["status"] = (
                "completed"
                if failed == 0 and not paused_stop
                else ("paused" if paused_stop else "failed")
            )
            team_state["updated_at"] = datetime.now(timezone.utc).isoformat()
            if team_validation is not None or validation_command is not None:
                team_state["validation"] = {
                    "qa_review": "approved",  # qa 角色任务全完成 (failed==0) → 评审通过
                    "command": validation_command,
                    "success": team_validation.success if team_validation else True,
                    "tests_total": team_validation.tests_total if team_validation else 0,
                    "tests_passed": team_validation.tests_passed if team_validation else 0,
                    "tests_failed": team_validation.tests_failed if team_validation else 0,
                    "errors": list(team_validation.errors) if team_validation else [],
                }
            TeamExecutionState.save(project_dir, team_state)
            # S10-057 §P5: team_report.md 生成 (team/tasks/agents/artifacts/
            # validation/conflicts/handoffs)
            self._write_team_report(
                project_dir,
                slug,
                state,
                result,
                team_run,
                team_validation,
                validation_command,
            )
        return result

    def _write_team_report(
        self,
        project_dir: Path,
        slug: str,
        state: ExecutionState,
        result: ExecutionResult,
        team_run: TeamRunContext,
        team_validation: Optional[ValidationResult],
        validation_command: Optional[str],
    ) -> Path:
        """生成 team_report.md (设计 §P5): team/tasks/agents/artifacts/validation/
        conflicts/handoffs → projects/<slug>/team_report.md。

        只读各资产 (workspace_context / conflict_resolution / handoff_messages /
        execution_state) 组装 markdown; 缺失资产 → 缺省占位, 不抛。
        """
        team = team_run.team or {}
        members = [dict(m) for m in (team.get("members") or []) if isinstance(m, dict)]
        role_of = {
            str(m.get("agent")): str(m.get("role") or "") for m in members
        }
        agent_ids = sorted(
            {
                str(t.get("agent"))
                for t in state.tasks
                if t.get("agent") and str(t.get("agent")) != "None"
            }
        )
        val_counts = Counter(str(t.get("validation")) for t in state.tasks)
        ctx = WorkspaceContext.load(project_dir)
        lines: list[str] = [
            f"# Team Report — {slug}",
            "",
            f"- 项目: {slug}",
            f"- 团队: {team.get('name') or team.get('team_id') or '-'} (`{team.get('team_id') or '-'}`)",
            f"- 状态: {result.status}",
            f"- Lifecycle: {state.lifecycle or state.status or '-'}",
            f"- 完成/失败: {result.completed_tasks}/{result.failed_tasks}",
            "",
            "## Team",
            "",
            "| agent | role |",
            "|---|---|",
        ]
        for m in members:
            lines.append(f"| {m.get('agent') or '-'} | {m.get('role') or '-'} |")
        lines += [
            "",
            "## Tasks",
            "",
            "| id | name | agent | status | validation | artifact |",
            "|---|---|---|---|---|---|",
        ]
        for t in state.tasks:
            lines.append(
                f"| {t.get('id') or '-'} | {t.get('name') or '-'} | "
                f"{t.get('agent') or '-'} | {t.get('status') or '-'} | "
                f"{t.get('validation') or '-'} | {t.get('artifact') or '-'} |"
            )
        lines += [
            "",
            "## Agents",
            "",
        ]
        if agent_ids:
            for aid in agent_ids:
                lines.append(f"- {aid} ({role_of.get(aid) or '-'})")
        else:
            lines.append("- (无)")
        lines += [
            "",
            "## Artifacts",
            "",
        ]
        artifacts = list(result.artifacts) or list(ctx.get("artifacts") or [])
        if artifacts:
            for a in artifacts:
                lines.append(f"- {a}")
        else:
            lines.append("- (无)")
        lines += [
            "",
            "## Validation",
            "",
            f"- 任务验证: passed={val_counts.get('passed', 0)}, "
            f"failed={val_counts.get('failed', 0)}",
        ]
        if validation_command is not None or team_validation is not None:
            if team_validation is not None:
                lines.append(
                    f"- 团队验证 ({validation_command}): "
                    f"{'PASS' if team_validation.success else 'FAIL'} "
                    f"(passed={team_validation.tests_passed}/"
                    f"{team_validation.tests_total}, "
                    f"failed={team_validation.tests_failed})"
                )
                for err in team_validation.errors:
                    lines.append(f"  - error: {err}")
            else:
                lines.append(f"- 团队验证 ({validation_command}): 未执行 (命令门未开启)")
        else:
            lines.append("- 团队验证: 未启用 (validation_command=None, mock 语义)")
        lines += [
            "",
            "## Conflicts",
            "",
        ]
        res_file = project_dir / "conflict_resolution.json"
        resolutions: list[dict[str, Any]] = []
        if res_file.is_file():
            try:
                res_data = json.loads(res_file.read_text(encoding="utf-8"))
                resolutions = [
                    dict(r)
                    for r in (res_data.get("resolutions") or [])
                    if isinstance(r, dict)
                ]
                lines.append(f"- strategy: {res_data.get('strategy') or '-'}")
                lines.append(
                    f"- ordered_tasks: {', '.join(res_data.get('ordered_tasks') or []) or '-'}"
                )
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 缺省
                lines.append("- (损坏/缺失)")
        if resolutions:
            for r in resolutions:
                lines.append(
                    f"- {r.get('file') or '-'}: {r.get('task_a') or '-'} vs "
                    f"{r.get('task_b') or '-'} → {r.get('strategy') or '-'}"
                )
        else:
            lines.append("- 无冲突")
        lines += [
            "",
            "## Handoffs",
            "",
        ]
        ho_file = project_dir / "handoff_messages.json"
        handoffs: list[dict[str, Any]] = []
        if ho_file.is_file():
            try:
                data = json.loads(ho_file.read_text(encoding="utf-8"))
                handoffs = [dict(h) for h in data if isinstance(h, dict)]
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 缺省
                handoffs = []
        if handoffs:
            for h in handoffs:
                lines.append(
                    f"- {h.get('from') or '-'} → {h.get('to') or '-'}: "
                    f"requirement={h.get('requirement') or '-'} | "
                    f"decision={h.get('decision') or '-'} | "
                    f"constraints={h.get('constraints') or '-'}"
                )
        else:
            lines.append("- 无交接")
        path = project_dir / "team_report.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

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
