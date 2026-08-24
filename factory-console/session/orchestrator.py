"""factory-console/session/orchestrator.py — Autonomous Production Loop 执行编排 (S10-052 P0-P6 + S10-065 批次 C)。

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
from .budget import BudgetEnforcer, BudgetUsage
from .conflicts import (
    ConflictDetector,
    ConflictRecord,
    ConflictResolver,
    FileOwnership,
)
from .context_builder import ContextBuilder
from .cost_ledger import CostLedger
from .decision import HandoffDecisionEngine
from .dependencies import TaskDependencyGraph
from .gap_analyzer import GapAnalyzer
from .intent import IntentObject
from .llm_gap import LLMGapAnalyzer
from .llm_task_proposal import LLMTaskProposalEngine
from .loop_guard import LoopGuard
from .messages import AgentMessageStore, HandoffStore
from .pipeline import Lifecycle
from .plan_critic import PlanCritic
from .planning_trace import PlanningTrace
from .quality import RepairManager, ValidationResult, Validator
from .reasoning import ReasoningProvider
from .replanning import ReplanDecision, ReplanningEngine
from .review_gate import ReviewGate
from .roles import RoleSystem
from .task_proposal import TaskProposalEngine, TaskProposalValidator
from .team_state import TeamExecutionState
from .teams import DEFAULT_TEAM_ID, TeamRegistry
from .workspace import WorkspaceContext


class ProjectNotFoundError(Exception):
    """项目未找到 (slug/name 均未匹配 projects/ 下目录) — 明确报错, 不静默。"""


class PlanNotFoundError(Exception):
    """execution_plan.json 缺失 — 项目未准备工程 (prepare_project 未执行)。"""


class ExecutionStateError(Exception):
    """execution_state.json 缺失/损坏 — resume/get_progress 无法读取。"""


#: planning_mode 取值 (S10-062 批次 C — 设计 §11):
#: deterministic — 现有行为 (S10-061 完全兼容, LLM 参数忽略);
#: llm — LLM 优先 + deterministic fallback (无 provider → REQUEST_REVIEW 安全兜底);
#: hybrid — LLM 优先 + deterministic fallback (缺省; 无 LLM 注入 → 完全 deterministic)
PLANNING_MODE_DETERMINISTIC = "deterministic"
PLANNING_MODE_LLM = "llm"
PLANNING_MODE_HYBRID = "hybrid"
PLANNING_MODES: tuple[str, ...] = (
    PLANNING_MODE_DETERMINISTIC,
    PLANNING_MODE_LLM,
    PLANNING_MODE_HYBRID,
)


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
    # S10-073 P0-B: 产物创建自动 Audit (ARTIFACT_CREATED, 失败安全)
    if result.ok:
        try:
            from ..audit.audit_emitter import AuditEmitter
            AuditEmitter(workspace=workspace).emit(
                "ARTIFACT_CREATED", project_id=project_dir.name,
                task_id=str(task.get("id") or ""),
                agent_id=str(task.get("agent") or ""),
                decision_reason=f"Agent 产物: {task.get('name') or task.get('id')}",
                artifact_reference=str(execution.get("artifact") or ""),
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
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
    S10-060 (Autonomous Replanning, 设计 §5 P4): plan_version (缺省 1) /
    replan_count (缺省 0) / last_replan_reason (计划变更可解释 — 为什么改变计划)。
    """

    project: str
    status: str = Lifecycle.DEVELOPMENT
    lifecycle: Optional[str] = Lifecycle.DEVELOPMENT
    started_at: str = ""
    tasks: list[dict[str, Any]] = field(default_factory=list)
    plan_version: int = 1
    replan_count: int = 0
    last_replan_reason: str = ""
    # S10-063 批次 B (Production Governance): 治理停止状态/原因/告警 —
    # 非缺省才落盘 (缺省状态与旧版字节一致, 兼容 S10-055~062 资产/测试)
    governance_status: str = ""
    governance_reason: str = ""
    governance_warnings: list[str] = field(default_factory=list)
    # M3c (S10-090 M3-3): 并行调度审计视图 (仅 parallel 模式非空才落盘 —
    # solo/team 缺省零变化): {rounds, max_concurrency, degraded, reason,
    # schedule_file}
    schedule: dict[str, Any] = field(default_factory=dict)
    # M3e (S10-097): M3 全链调度审计视图 (仅 m3 模式非空才落盘 — solo/team/
    # parallel 缺省零变化): {rounds, assignments, evidence, degraded, reason}
    m3: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘/审计视图)。

        S10-060: plan_version/replan_count/last_replan_reason 非缺省才落盘 —
        缺省状态 (v1/0/空) 与旧版字节一致 (旧资产/旧测试兼容); 重规划后
        (plan v2+/count>0) 携带版本字段 (可回答"为什么改变计划")。
        S10-063: governance_status/reason/warnings 非空才落盘 (缺省零变化)。
        """
        data: dict[str, Any] = {
            "project": self.project,
            "status": self.status,
            "lifecycle": self.lifecycle,
            "started_at": self.started_at,
            "tasks": list(self.tasks),
        }
        if int(self.plan_version or 1) != 1:
            data["plan_version"] = int(self.plan_version or 1)
        if int(self.replan_count or 0) != 0:
            data["replan_count"] = int(self.replan_count or 0)
        if str(self.last_replan_reason or ""):
            data["last_replan_reason"] = str(self.last_replan_reason or "")
        if str(self.governance_status or ""):
            data["governance_status"] = str(self.governance_status or "")
        if self.schedule:
            data["schedule"] = dict(self.schedule)
        if str(self.governance_reason or ""):
            data["governance_reason"] = str(self.governance_reason or "")
        if self.governance_warnings:
            data["governance_warnings"] = list(self.governance_warnings)
        if self.m3:
            data["m3"] = dict(self.m3)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionState":
        """dict → ExecutionState (未知键忽略, 缺失字段用默认值 — 前向兼容)。"""
        return cls(
            project=str(data.get("project") or ""),
            status=str(data.get("status") or Lifecycle.DEVELOPMENT),
            lifecycle=data.get("lifecycle") or Lifecycle.DEVELOPMENT,
            started_at=str(data.get("started_at") or ""),
            tasks=list(data.get("tasks") or []),
            plan_version=int(data.get("plan_version") or 1),
            replan_count=int(data.get("replan_count") or 0),
            last_replan_reason=str(data.get("last_replan_reason") or ""),
            governance_status=str(data.get("governance_status") or ""),
            governance_reason=str(data.get("governance_reason") or ""),
            governance_warnings=[
                str(w) for w in (data.get("governance_warnings") or [])
            ],
            schedule=dict(data.get("schedule") or {}),
            m3=dict(data.get("m3") or {}),
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
    """团队执行钩子 (S10-056 批次 B + S10-057 + S10-059 P4): 冲突检测/解决 +
    Workspace 注入 + Handoff + TeamState 更新 + 自主决策 + 工作区隔离。

    仅 team mode 使用 (solo mode 无此上下文, 行为零变化):
    - before_task: ConflictDetector.detect — 同文件多任务 → ConflictRecord
      + HandoffDecisionEngine.decide (S10-059: 自主决策记录 — CONTINUE/
      BLOCK/RETRY/REPAIR/SERIALIZE/SKIP/REQUEST_REVIEW + reason, 落盘
      handoff_decisions.json); SERIALIZE/BLOCK → acquire_reservation 文件锁
      (同文件已被其他 agent 占 → 锁未释放 → 记录 BLOCK, 本任务暂缓不执行 —
      串行化, 不无限等待)
    - inject_context: 任务执行前 WorkspaceContext 快照 (completed_tasks/
      artifacts/messages/decisions) + reservations (workspace_locks.json) +
      changed_files + recent_decision → task["context"] 透传 (设计 §P3 —
      execute_fn 可读)
    - after_task: release_reservation (释放文件锁 — 无论成败, 锁不残留) +
      任务成功 → WorkspaceContext.mark_task_completed/add_artifact
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
    # S10-059 P4: 决策引擎 + 依赖图 + Agent 角色映射 (决策输入)
    decision_engine: Optional[HandoffDecisionEngine] = None
    decisions_file: Optional[Path] = None
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    agent_roles: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        #: 本任务是否被 BLOCK (锁未释放) — _run_queue 消费 (暂缓不执行)
        self._blocked: bool = False

    # ------------------------------------------------------------ 决策/锁

    def _engine(self, project_dir: Path) -> HandoffDecisionEngine:
        """决策引擎 (惰性构造 — 缺省项目级 handoff_decisions.json)。"""
        if self.decision_engine is None:
            file = self.decisions_file or Path(project_dir) / "handoff_decisions.json"
            self.decision_engine = HandoffDecisionEngine(file=file)
        return self.decision_engine

    def before_task(
        self, project_dir: Path, task: dict[str, Any]
    ) -> list[ConflictRecord]:
        """任务执行前 (S10-059 P4): 冲突检测 → 自主决策记录 → 文件锁获取。

        ① ConflictDetector.detect — 同文件已被其他 task 归属 → ConflictRecord;
        ② HandoffDecisionEngine.decide — 决策 (SKIP/BLOCK/RETRY/REPAIR/
           SERIALIZE/REQUEST_REVIEW/CONTINUE + reason) → task["decision"] +
           handoff_decisions.json 落盘;
        ③ acquire_reservation 文件写权限锁 (有 files 的任务一律获取 — 同文件
           互斥, 锁防未来并行): 同文件已被其他 agent 占 → 锁未释放 → 记录
           BLOCK (等待前序释放, 不无限等待) + 本任务暂缓
           (is_blocked() → True, 不执行 — 顺序框架下串行化)。

        返回 ConflictRecord 列表 (向后兼容 — 原 detect 返回语义不变)。
        """
        self._blocked = False
        files = [str(f) for f in (task.get("files") or []) if not isinstance(f, dict)]
        task_id = str(task.get("id") or "")
        conflicts = self.detector.detect(project_dir, task_id, files)
        decision = self._decide(project_dir, task, conflicts)
        task["decision"] = decision
        if files:
            # 文件写权限锁: 前序已完成 → 锁已释放 → 获取成功; 前序未完成/未释放
            # → BLOCK 暂缓 (决策已记录, 不无限等待; resume 后可继续)
            acquired = WorkspaceContext.acquire_reservation(
                project_dir, str(task.get("agent") or ""), task_id, files
            )
            if acquired is None:
                blocked = self._record_block(project_dir, task, files)
                task["decision"] = blocked
                self._blocked = True
        return conflicts

    def _decide(
        self, project_dir: Path, task: dict[str, Any], conflicts: list[ConflictRecord]
    ) -> dict[str, Any]:
        """决策引擎调用 + 落盘 (handoff_decisions.json append)。"""
        engine = self._engine(project_dir)
        ctx = WorkspaceContext.load(project_dir)
        task_id = str(task.get("id") or "")
        deps = list(self.dependencies.get(task_id) or [])
        agent_role = str(self.agent_roles.get(str(task.get("agent") or "")) or "")
        decision = engine.decide(
            task,
            completed_tasks=list(ctx.get("completed_tasks") or []),
            next_tasks=[],
            dependencies={task_id: deps} if deps else {},
            conflicts=[c.to_dict() for c in conflicts],
            workspace=ctx,
            agent_role=agent_role,
            records=engine.previous_decisions(),
        )
        return engine.record(decision)

    def _record_block(
        self, project_dir: Path, task: dict[str, Any], files: list[str]
    ) -> dict[str, Any]:
        """锁未释放 → BLOCK 决策 (等待前序任务释放, 不无限等待)。"""
        engine = self._engine(project_dir)
        holders = WorkspaceContext.reserved_files(project_dir)
        agent = str(task.get("agent") or "")
        held = [
            f for f in files if f in holders and str(holders[f].get("agent") or "") != agent
        ]
        return engine.record(
            {
                "decision": HandoffDecisionEngine.DECISION_BLOCK,
                "reason": (
                    f"文件锁未释放: {', '.join(held) or '同文件冲突'} — "
                    f"等待前序任务释放后执行 (串行化, 不无限等待)"
                ),
                "conflicting_tasks": [str(holders[f].get("task_id") or "") for f in held],
                "strategy": "wait for lock release",
                "task_id": str(task.get("id") or ""),
            }
        )

    def is_blocked(self) -> bool:
        """本任务是否被 BLOCK (锁未释放) — 队列暂缓执行。"""
        return self._blocked

    def release_reservation(self, project_dir: Path, task: dict[str, Any]) -> None:
        """任务执行后释放文件锁 (S10-059 P4: 无论成败, 锁不残留)。"""
        try:
            WorkspaceContext.release_reservation(
                project_dir, str(task.get("agent") or ""), str(task.get("id") or "")
            )
        except Exception:  # noqa: BLE001 — 失败安全: 释放异常不中断队列
            pass

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
            # S10-058: previous_decisions (DecisionStore 结构化决策注入 — 决策驱动执行)
            "previous_decisions": self._previous_decisions(project_dir, str(task.get("agent") or "")),
            # S10-059 P4: reservations (workspace_locks.json) + changed_files +
            # workspace_snapshot + recent_decision (工作区隔离可解释上下文)
            "reservations": WorkspaceContext.reserved_files(project_dir),
            "changed_files": list(ctx.get("changed_files") or []),
            "workspace_snapshot": dict(ctx.get("workspace_snapshot") or {}),
            "recent_decision": dict(task.get("decision") or {}),
        }
        task["context"] = context
        return context

    def _previous_decisions(self, project_dir: Path, agent: str) -> dict[str, Any]:
        """S10-058: 读取 decision_objects.json 中发给该 Agent 的决策 → 上下文。"""
        try:
            from .messages import DecisionStore

            dstore = DecisionStore(
                file=Path(project_dir) / "decision_objects.json"
            )
            return dstore.previous_decisions()
        except Exception:  # noqa: BLE001 — 失败安全: 缺决策 → 空
            return {}

    def after_task(self, project_dir: Path, task: dict[str, Any]) -> None:
        """任务执行后 (S10-059 P4): 释放文件锁 (无论成败, 锁不残留) +
        任务成功后 Workspace 更新 + 可选消息 (仅 completed 任务)。"""
        # S10-059 P4: 释放该任务持有的文件锁 (串行化 — 前序释放后后继才能写)
        self.release_reservation(project_dir, task)
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


class _GovernanceContext:
    """S10-063 批次 B: 生产治理集成上下文 — budget/cost_ledger/review_gate/
    policy/loop_guard 聚合 (设计 §3-§7, 全部可选, 缺省 None → 无治理行为)。

    - check_budget(action, task) → None | {"status": "blocked"|"waiting_for_review",
      "reason"}: BudgetEnforcer.enforce — block → blocked (停止); review →
      waiting_for_review (停止, 等审批); warn → 记录告警继续 (不停止)
    - check_execution_time() → None | stop (S10-065): 每任务执行前 elapsed
      (从执行开始累积) >= budget.max_execution_time → 停止 (有 review_gate
      → waiting_for_review + request; 无 → blocked — 同 budget enforce 语义)
    - check_policy(op, task) → None | stop: can_execute/can_retry/can_repair/
      can_replan — 禁 → 停止 (有 review_gate → waiting_for_review + request;
      无 gate → blocked)
    - check_loop_failure(task, failure_key) → None | stop: LoopGuard.check_failure
      — action block → blocked; review → waiting_for_review
    - record_execution(task, outcome) — cost_ledger.record EXECUTION
      (project/task/agent/tokens/cost/latency)
    - record_planning(purpose, task, **kw) — cost_ledger.record
      REPLANNING/GAP_ANALYSIS/PLANNING
    - request_review(reason, trigger, task) — review_gate.request (失败安全)

    停止语义: stop_status/stop_reason 为单一停止信号 (队列消费后 break);
    warn 记录进 warnings (state.governance_warnings 落盘, 可回答"为什么告警")。
    """

    STATUS_BLOCKED = "blocked"
    STATUS_WAITING_REVIEW = "waiting_for_review"

    def __init__(
        self,
        project_id: str,
        *,
        budget: Optional[Any] = None,
        cost_ledger: Optional[Any] = None,
        review_gate: Optional[Any] = None,
        policy: Optional[Any] = None,
        loop_guard: Optional[Any] = None,
        # S10-065: 执行开始时间 (wall-clock, time.monotonic) — max_execution_time
        # 计时基准 (每任务执行前检查 elapsed; None → 不计时)
        execution_started: Optional[float] = None,
    ) -> None:
        self.project_id = str(project_id or "")
        self.budget = budget
        self.cost_ledger = cost_ledger
        self.review_gate = review_gate
        self.policy = policy
        self.loop_guard = loop_guard
        self._execution_started = (
            float(execution_started) if execution_started is not None else None
        )
        #: 单一停止信号 (队列消费; "" = 未停止)
        self.stop_status: str = ""
        self.stop_reason: str = ""
        #: warn 级告警记录 (落盘 state.governance_warnings)
        self.warnings: list[str] = []
        #: loop_guard 失败历史 (同 task 同 failure 计数 — 组合总闸输入)
        self.failure_history: list[dict[str, Any]] = []

    # ------------------------------------------------------------ 组件判定

    def _usage(self) -> BudgetUsage:
        """已消耗量 (从 cost_ledger 记录聚合; 无 ledger → 空消耗)。

        S10-065: budget.max_execution_time > 0 时 execution_time 维度以
        wall-clock elapsed 覆盖 (max 取大 — 与 latency 聚合兼容, 时间维度
        真正生效; 其余维度不变)。
        """
        if self.cost_ledger is None:
            usage = BudgetUsage.from_records([], budget=self.budget)
        else:
            records = self.cost_ledger.records(self.project_id)
            usage = BudgetUsage.from_records(records, budget=self.budget)
        if (
            self.budget is not None
            and float(getattr(self.budget, "max_execution_time", 0.0) or 0.0) > 0
        ):
            usage.execution_time = max(
                usage.execution_time, round(self.elapsed(), 4)
            )
        return usage

    def elapsed(self) -> float:
        """自执行开始累积秒数 (wall-clock; 未设置起点 → 0.0)。"""
        if self._execution_started is None:
            return 0.0
        return max(0.0, time.monotonic() - self._execution_started)

    def check_execution_time(self) -> Optional[dict[str, Any]]:
        """执行时间闸 (S10-065, GAP G7): elapsed >= max_execution_time → 停止。

        遵循 budget enforce 语义: 有 review_gate → request_review +
        waiting_for_review; 无 gate → blocked。max_execution_time <= 0
        (无限) → 不检查。返回停止信号 dict 或 None。
        """
        if self.budget is None:
            return None
        max_time = float(getattr(self.budget, "max_execution_time", 0.0) or 0.0)
        if max_time <= 0:
            return None
        elapsed = self.elapsed()
        if elapsed < max_time:
            return None
        return self._stop_review(
            (
                f"执行超时: 已执行 {elapsed:.2f}s >= max_execution_time "
                f"{max_time:.2f}s — 停止执行 (budget:execution_time)"
            ),
            "budget:execution_time",
            None,
        )

    def check_budget(
        self, action: str, task: Optional[dict[str, Any]] = None
    ) -> Optional[dict[str, Any]]:
        """预算执行闸 (设计 §3): enforce → block/review 停止, warn 记录继续。"""
        if self.budget is None or self.cost_ledger is None:
            return None
        result = BudgetEnforcer.enforce(self.budget, self._usage(), action)
        level = str(result.get("level") or "ok")
        if level == BudgetEnforcer.LEVEL_BLOCK:
            return self._stop(self.STATUS_BLOCKED, result.get("reason") or "")
        if level == BudgetEnforcer.LEVEL_REVIEW:
            # 设计 §3: 90% → REVIEW_REQUIRED — 停止等审批 (有 gate → 记录评审)
            if self.review_gate is not None:
                self.request_review(result.get("reason") or "", f"budget:{action}", task)
            return self._stop(self.STATUS_WAITING_REVIEW, result.get("reason") or "")
        if level == BudgetEnforcer.LEVEL_WARN:
            self.warnings.append(str(result.get("reason") or ""))
        return None

    def check_policy(
        self, op: str, task: Optional[dict[str, Any]] = None
    ) -> Optional[dict[str, Any]]:
        """策略判定 (设计 §6): can_* 禁 → 停止 (有 gate → review, 无 → blocked)。"""
        if self.policy is None:
            return None
        fn = getattr(self.policy, f"can_{op}", None)
        if fn is None:
            return None
        context: dict[str, Any] = {
            "task": task or {},
            "task_id": str((task or {}).get("id") or ""),
            "agent_id": str((task or {}).get("agent") or ""),
            "name": str((task or {}).get("name") or ""),
            "description": str((task or {}).get("name") or ""),
            "task_count": 1,
        }
        try:
            allowed, reason = fn(context)
        except Exception:  # noqa: BLE001 — 失败安全: 判定异常 → 视为允许 (不阻断)
            return None
        if allowed:
            return None
        return self._stop_review(str(reason or f"policy 禁止 {op}"), f"policy:{op}", task)

    def check_loop_failure(
        self, task: dict[str, Any], failure_key: str
    ) -> Optional[dict[str, Any]]:
        """循环防护 (设计 §7): check_failure → block/review 停止, 其余记录继续。"""
        if self.loop_guard is None:
            return None
        task_id = str(task.get("id") or "")
        result = self.loop_guard.check_failure(task_id, failure_key, self.failure_history)
        action = str(result.get("action") or "")
        self.failure_history.append(
            {"task_id": task_id, "failure": failure_key, "action": action}
        )
        if action == LoopGuard.ACTION_BLOCK:
            return self._stop(self.STATUS_BLOCKED, result.get("reason") or "")
        if action == LoopGuard.ACTION_REVIEW:
            return self._stop_review(result.get("reason") or "", "loop_guard", task)
        return None

    # ------------------------------------------------------------ 停止信号

    def _stop(
        self, status: str, reason: str
    ) -> dict[str, Any]:
        """记录停止信号 (队列 break 消费)。"""
        self.stop_status = status
        self.stop_reason = str(reason or "")
        return {"status": status, "reason": self.stop_reason}

    def _stop_review(
        self, reason: str, trigger: str, task: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """评审停止: 有 review_gate → request + waiting_for_review; 无 → blocked。"""
        if self.review_gate is not None:
            self.request_review(reason, trigger, task)
            return self._stop(self.STATUS_WAITING_REVIEW, reason)
        return self._stop(self.STATUS_BLOCKED, reason)

    def request_review(
        self,
        reason: str,
        trigger: str,
        task: Optional[dict[str, Any]] = None,
        risk: str = "medium",
    ) -> Any:
        """发起人工评审 (失败安全: 评审记录失败不中断执行流)。"""
        if self.review_gate is None:
            return None
        try:
            return self.review_gate.request(
                reason=str(reason or ""),
                trigger=str(trigger or ""),
                project_id=self.project_id,
                affected_tasks=[str((task or {}).get("id") or "")]
                if task is not None
                else [],
                risk=risk,
            )
        except Exception:  # noqa: BLE001 — 失败安全
            return None

    # ------------------------------------------------------------ 成本记录

    def record_execution(
        self, task: dict[str, Any], outcome: dict[str, Any]
    ) -> None:
        """EXECUTION 成本记录 (设计 §4): project/task/agent/tokens/cost/latency。"""
        if self.cost_ledger is None:
            return
        usage = outcome.get("usage") or outcome.get("token_usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0) or (
            input_tokens + output_tokens
        )
        cost = outcome.get("estimated_cost")
        if cost is None:
            cost = self._parse_cost(outcome.get("cost"))
        self.cost_ledger.record(
            {
                "project_id": self.project_id,
                "task_id": str(task.get("id") or ""),
                "agent_id": str(task.get("agent") or ""),
                "purpose": "EXECUTION",
                "provider": str(outcome.get("provider") or ""),
                "model": str(outcome.get("model") or ""),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": float(cost or 0.0),
                "latency": float(outcome.get("duration") or 0),
                "parent_execution_id": str(
                    (task.get("parent_execution_id") or "")
                ),
            }
        )

    def record_planning(
        self,
        purpose: str,
        task: Optional[dict[str, Any]] = None,
        **kw: Any,
    ) -> None:
        """规划/重规划成本记录 (设计 §4): REPLANNING/GAP_ANALYSIS/PLANNING。"""
        if self.cost_ledger is None:
            return
        rec: dict[str, Any] = {
            "project_id": self.project_id,
            "task_id": str((task or {}).get("id") or ""),
            "agent_id": str((task or {}).get("agent") or ""),
            "purpose": purpose,
        }
        rec.update(kw)
        self.cost_ledger.record(rec)

    @staticmethod
    def _parse_cost(cost: Any) -> float:
        """成本字符串解析 (失败安全: 不可解析 → 0.0)。"""
        if cost is None:
            return 0.0
        if isinstance(cost, (int, float)):
            return float(cost)
        try:
            text = str(cost).strip().strip("$").strip()
            return float(text) if text else 0.0
        except Exception:  # noqa: BLE001 — 失败安全
            return 0.0


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

    def _arch_review_blocked(self, project_dir: Path) -> Optional[str]:
        """S10-111 M3-7 架构审批门: 非 execution_ready/development → 阻断消息。

        - status=execution_ready → 放行 (审批通过, v1.1.77 行为一致)
        - status=development → 放行 (执行中/恢复路径不受门控)
        - project.json 缺失 / status 缺失 → 放行 (失败安全, 既有行为不变)
        - 其它 (pending_arch_review / product_defined / engineering_ready …)
          → 明确错误 "工程计划待架构审批" (M3a-d 引擎内部逐字节不改 — 仅入口检查)
        """
        project_file = project_dir / "project.json"
        if not project_file.is_file():
            return None
        try:
            data = json.loads(project_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 损坏 → 不阻断 (orchestrator 为准)
            return None
        status = str(data.get("status") or "")
        if not status:
            return None
        # 放行面: 已审批 (execution_ready) / 执行中或已执行 (development ~ delivered) —
        # orchestrator 直调重跑等既有行为保持不变 (验收 ⑪: 审批通过后与 v1.1.77 一致)
        if status in (
            Lifecycle.EXECUTION_READY,
            Lifecycle.DEVELOPMENT,
            Lifecycle.TESTING,
            Lifecycle.VALIDATION_PASS,
            Lifecycle.USER_ACCEPTANCE,
            Lifecycle.DELIVERED,
        ):
            return None
        # 阻断面: 未审批/前置状态 (idea/product_defined/engineering_ready/
        # pending_arch_review 等) — 工程计划未获架构审批不可执行
        return (
            f"工程计划待架构审批: 项目状态 {status!r}, 请先批准工程计划 "
            f"(approve_project_plan) 后再执行"
        )

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
        S10-061 批次 B: 自动提案元数据条件透传 (source_gap/rationale/confidence/
        priority/acceptance_criteria/validation_command/objective/description —
        仅候选携带时写入, 旧式任务记录字节不变)。
        """
        record: dict[str, Any] = {
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
        # S10-061 批次 B: 自动提案元数据条件透传 (仅存在时 — 旧记录零变化)
        for key in (
            "description",
            "objective",
            "source_gap",
            "rationale",
            "confidence",
            "priority",
            "validation_command",
        ):
            val = plan_task.get(key)
            if val not in (None, ""):
                record[key] = val
        crits = plan_task.get("acceptance_criteria")
        if crits:
            record["acceptance_criteria"] = [
                str(c) for c in crits if not isinstance(c, dict)
            ]
        return record

    def execute_project(
        self,
        project_id: str,
        *,
        execute_fn: Optional[ExecuteFn] = None,
        max_retry: int = DEFAULT_MAX_RETRY,
        mode: str = "solo",
        # M3c (S10-090 M3-3): parallel 模式配置 — 默认 1 = 顺序执行 (旧行为零变化)
        max_concurrency: int = 1,
        schedule_file: Optional[Path] = None,
        team_id: str = DEFAULT_TEAM_ID,
        teams_file: Optional[Path] = None,
        agents_file: Optional[Path] = None,
        dependencies_file: Optional[Path] = None,
        conflicts_file: Optional[Path] = None,
        messages_file: Optional[Path] = None,
        enable_messages: bool = False,
        validation_command: Optional[str] = None,
        # S10-060 (Autonomous Replanning, 设计 §P5): 计划级重规划接入
        # replanner=None → 重规划关闭 (solo/team 既有行为零变化);
        # 提供后: 任务失败 → ReplanningEngine.decide → 更新 DAG/Plan → 继续执行
        replanner: Optional[ReplanningEngine] = None,
        max_replan: int = 5,
        insert_tasks: Optional[list[dict[str, Any]]] = None,
        replanning_file: Optional[Path] = None,
        # S10-061 批次 B (Autonomous Gap Resolution 集成): 失败 → GapAnalyzer →
        # TaskProposalEngine → Validator → INSERT → 执行 (gap_analyzer=None →
        # 自动提案关闭, 既有行为零变化; 提供后 task_proposal/task_validator
        # 缺省用真实引擎 — 新任务由引擎生成, 非调用方注入)
        gap_analyzer: Optional[GapAnalyzer] = None,
        task_proposal: Optional[TaskProposalEngine] = None,
        task_validator: Optional[TaskProposalValidator] = None,
        max_auto_insert_tasks: int = 5,
        max_tasks_per_round: int = 3,
        max_total_generated_tasks: int = 10,
        auto_mode: str = "auto_execute",
        proposals_file: Optional[Path] = None,
        # S10-062 批次 C (LLM Planning 集成, 设计 §11):
        # planning_mode — "deterministic" (现有行为, LLM 参数忽略) | "llm"
        # (LLM 优先 + fallback; 无 provider → REQUEST_REVIEW) | "hybrid"
        # (缺省: LLM 优先 + deterministic fallback; 无 LLM 注入 → 完全
        # deterministic — S10-061 兼容)。LLM 链: ContextBuilder → LLMGapAnalyzer
        # → LLMTaskProposalEngine → ReplanningEngine (LLM=建议, Deterministic=执行)
        planning_mode: str = PLANNING_MODE_HYBRID,
        llm_reasoning: Optional[ReasoningProvider] = None,
        llm_gap_analyzer: Optional[LLMGapAnalyzer] = None,
        llm_task_proposal: Optional[LLMTaskProposalEngine] = None,
        llm_trace: Optional[PlanningTrace] = None,
        llm_confidence_threshold: float = 0.5,
        # 执行前 PlanCritic 检查 (设计 §6): 计划缺口 → 提案链 (propose +
        # validator) → ReplanningEngine.decide → INSERT (不直接改 DAG);
        # 仅 replanner 同时提供时启用; None → 关闭 (既有行为零变化)
        plan_critic: Optional[PlanCritic] = None,
        # S10-063 批次 B (Production Governance 集成, 设计 §3-§7):
        # budget/cost_ledger/review_gate/policy/loop_guard — 全部可选,
        # 全缺省 → 现有行为完全不变 (S10-055~062 兼容)
        budget: Optional[Any] = None,
        cost_ledger: Optional[Any] = None,
        review_gate: Optional[Any] = None,
        policy: Optional[Any] = None,
        loop_guard: Optional[Any] = None,
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

        mode="parallel" (M3c, S10-090 M3-3 并行调度执行):
        ① 读 plan.json (M3b 关键路径标注产物) + execution_plan.json
        ② TaskScheduler.schedule — 依赖就绪队列 + 同文件冲突串行化
           (ConflictResolver 复用) + 并发分桶 (max_concurrency) → rounds
        ③ 按 rounds 扁平序重排执行队列 (同轮内按现有执行链跑) → 落盘
           schedule.json {rounds, order, conflicts, max_concurrency, created_at}
        ④ 失败安全: 环/无 plan.json → 降级顺序执行 (schedule.json + state.schedule
           degraded=True 诚实标注, 不伪造并行)
        ⑤ 向后兼容: max_concurrency=1 = 旧顺序执行 (每轮单任务)

        mode="m3" (M3e, S10-097 M3 全链 — 调度器接管真实执行 + 动态分配):
        ① 输入: project + plan.json (M3b, 存在即复用) + execution_state
        ② 计划链: DecomposeEngine (复合→原子) → CriticalPathEngine (关键路径,
           落盘 plan.json/dependencies.json) → TaskScheduler (依赖就绪轮次 +
           同文件冲突 ConflictResolver 串行化)
        ③ 每轮: AgentMatcher.match 实时动态分配 (skill × 历史成功率, 复用
           agents.py 不修改) → 分配落盘 state.m3.assignments [{round, task,
           agent_id}] → ExecutionLoop 执行 (复用 _execute_with_retry + Validator)
        ④ 每任务回填 execution_state + EvidenceBundle 落盘 evidence/ (M1a 复用)
        ⑤ 审计 5 事件: EXECUTION_ROUND_STARTED / EXECUTION_TASK_ASSIGNED /
           EXECUTION_TASK_COMPLETED / EXECUTION_ROUND_COMPLETED /
           EXECUTION_M3_DEGRADED
        ⑥ 失败安全: 单任务失败不中断整链 (后续轮次继续); M3 链任何异常 →
           降级 solo 顺序执行 (EXECUTION_M3_DEGRADED + state.m3.degraded 诚实标注)
        ⑦ 输出: 同 execute_project 既有结果结构 + state.m3 = {rounds,
           assignments, evidence}
        边界: 轮内任务依序执行 (并行线程化后置); 不做原子沙箱 / M3f / M3g。

        每任务: pending → running → completed/failed (状态逐任务持久化, 可恢复);
        失败: retry_count+1, 最多重试 max_retry 次, 仍失败 → failed (继续下一任务);
        全部完成 → Lifecycle TESTING → (测试门占位通过) → DELIVERED。
        """
        project_dir, slug = self._locate_project(project_id)
        # S10-111 M3-7: 架构审批门 — 非 execution_ready 明确阻断 (M3a-d 内部不改)
        blocked = self._arch_review_blocked(project_dir)
        if blocked:
            raise ExecutionStateError(blocked)
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
        # M3c (S10-090 M3-3): parallel 模式 — plan.json → TaskScheduler → rounds
        # 重排执行队列; 失败安全: 环/无 plan → 降级顺序执行 (诚实标注)。
        schedule_view: Optional[dict[str, Any]] = None
        if mode == "parallel":
            plan_tasks, schedule_view = self._parallel_prepare(
                project_dir,
                slug,
                plan_tasks,
                max_concurrency=int(max_concurrency or 1),
                schedule_file=schedule_file,
            )
        state = ExecutionState(
            project=slug,
            status=Lifecycle.DEVELOPMENT,
            lifecycle=Lifecycle.DEVELOPMENT,
            started_at=datetime.now(timezone.utc).isoformat(),
            tasks=[self._task_record(t) for t in plan_tasks],
        )
        if schedule_view:
            state.schedule = schedule_view
        self._save_state(project_dir, state)
        # Lifecycle: EXECUTION_READY → DEVELOPMENT (project.json/product.json status)
        self._set_lifecycle(project_dir, slug, Lifecycle.DEVELOPMENT)
        started = time.monotonic()
        # S10-060: 重规划引擎解析 (replanning_file 便捷参数 → 引擎构造; 缺省关闭)
        if replanner is None and replanning_file is not None:
            replanner = ReplanningEngine(file=replanning_file)
        # S10-061 批次 B: 自动提案组件解析 — gap_analyzer 提供后, 提案引擎/验证器
        # 缺省用真实实现 (TaskProposalEngine/TaskProposalValidator — 非测试注入)
        # S10-062 批次 C: plan_critic 提供后同样注入 (执行前缺口 → 提案链)
        if gap_analyzer is not None or plan_critic is not None:
            task_proposal = task_proposal if task_proposal is not None else TaskProposalEngine()
            task_validator = (
                task_validator
                if task_validator is not None
                else TaskProposalValidator()
            )
        # S10-062 批次 C: LLM planning 组件装配 (planning_mode ≠ deterministic
        # 且注入 llm_reasoning/llm_gap_analyzer → 补全 LLM 链; 缺省 hybrid +
        # 无注入 = 完全 deterministic — S10-061 兼容)
        llm_gap_analyzer, llm_task_proposal, _planning_mode = (
            self._assemble_llm_planning(
                planning_mode,
                llm_reasoning,
                llm_gap_analyzer,
                llm_task_proposal,
                llm_trace,
                llm_confidence_threshold,
            )
        )
        # M3e (S10-097): M3 全链执行 (mode="m3") — 调度器接管真实执行 + 动态分配。
        # DecomposeEngine → CriticalPathEngine → TaskScheduler 轮次 → 每轮
        # AgentMatcher 动态分配 → ExecutionLoop 执行 → 证据落盘 → 审计;
        # 失败安全: M3 链异常 → 降级 solo 顺序执行 (degraded 诚实标注)。
        if mode == "m3":
            result = self._execute_m3(
                project_dir,
                slug,
                state,
                list(plan_tasks),
                execute_fn=execute_fn,
                max_retry=max_retry,
                agents_file=agents_file,
                max_concurrency=int(max_concurrency or 1),
                run_solo=lambda: self._run_queue(
                    project_dir,
                    slug,
                    state,
                    execute_fn=execute_fn,
                    max_retry=max_retry,
                    validation_command=validation_command,
                    plan=plan,
                    replanner=replanner,
                    max_replan=int(max_replan or 5),
                    insert_tasks=list(insert_tasks or []),
                    dependencies_file=dependencies_file,
                    gap_analyzer=gap_analyzer,
                    task_proposal=task_proposal,
                    task_validator=task_validator,
                    max_auto_insert_tasks=int(max_auto_insert_tasks or 5),
                    max_tasks_per_round=int(max_tasks_per_round or 3),
                    max_total_generated_tasks=int(max_total_generated_tasks or 10),
                    auto_mode=str(auto_mode or "auto_execute"),
                    proposals_file=proposals_file,
                    planning_mode=_planning_mode,
                    llm_gap_analyzer=llm_gap_analyzer,
                    llm_task_proposal=llm_task_proposal,
                    llm_reasoning=llm_reasoning,
                    llm_trace=llm_trace,
                    llm_confidence_threshold=float(llm_confidence_threshold or 0.5),
                    governance=_GovernanceContext(
                        slug,
                        budget=budget,
                        cost_ledger=cost_ledger,
                        review_gate=review_gate,
                        policy=policy,
                        loop_guard=loop_guard,
                        execution_started=started,
                    ),
                ),
            )
            result.duration = time.monotonic() - started
            return result
        # S10-062 批次 C: PlanCritic 执行前检查 (可选) — 计划缺口 → 提案链 →
        # INSERT (不直接改 DAG); 仅 replanner + plan_critic 均提供时启用
        if plan_critic is not None and replanner is not None:
            preflight = self._plan_critic_preflight(
                project_dir,
                slug,
                state,
                plan,
                replanner=replanner,
                plan_critic=plan_critic,
                task_proposal=task_proposal,
                task_validator=task_validator,
                max_replan=int(max_replan or 5),
                dependencies_file=dependencies_file,
                team_run=team_run,
                proposals_file=proposals_file,
            )
            if preflight == "review":
                # 执行前缺口无法自动解决 → 停止执行, 需人工评审 (REQUEST_REVIEW 安全)
                result = ExecutionResult(
                    project=slug,
                    status="review_required",
                    completed_tasks=0,
                    failed_tasks=0,
                    errors=[
                        "PlanCritic 执行前检查: "
                        + str(
                            state.last_replan_reason
                            or "计划缺口无法自动解决 — 需人工评审 (REQUEST_REVIEW)"
                        )
                    ],
                )
                result.duration = time.monotonic() - started
                return result
        result = self._run_queue(
            project_dir,
            slug,
            state,
            execute_fn=execute_fn,
            max_retry=max_retry,
            team_run=team_run,
            validation_command=validation_command,
            plan=plan,
            replanner=replanner,
            max_replan=int(max_replan or 5),
            insert_tasks=list(insert_tasks or []),
            dependencies_file=dependencies_file,
            gap_analyzer=gap_analyzer,
            task_proposal=task_proposal,
            task_validator=task_validator,
            max_auto_insert_tasks=int(max_auto_insert_tasks or 5),
            max_tasks_per_round=int(max_tasks_per_round or 3),
            max_total_generated_tasks=int(max_total_generated_tasks or 10),
            auto_mode=str(auto_mode or "auto_execute"),
            proposals_file=proposals_file,
            planning_mode=_planning_mode,
            llm_gap_analyzer=llm_gap_analyzer,
            llm_task_proposal=llm_task_proposal,
            llm_reasoning=llm_reasoning,
            llm_trace=llm_trace,
            llm_confidence_threshold=float(llm_confidence_threshold or 0.5),
            # S10-063 批次 B: 治理上下文 (全缺省 → 无治理行为)
            governance=_GovernanceContext(
                slug,
                budget=budget,
                cost_ledger=cost_ledger,
                review_gate=review_gate,
                policy=policy,
                loop_guard=loop_guard,
                # S10-065: max_execution_time 计时基准 (从执行开始累积)
                execution_started=started,
            ),
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
        # S10-073 P0-B: Agent 分配自动 Audit (AGENT_ASSIGNED, 失败安全)
        try:
            from ..audit.audit_emitter import AuditEmitter
            _emitter = AuditEmitter(workspace=project_dir.parent.parent)
            for _task in plan_tasks:
                if _task.get("agent"):
                    _emitter.emit(
                        "AGENT_ASSIGNED", project_id=project_dir.name,
                        task_id=str(_task.get("id") or ""),
                        agent_id=str(_task.get("agent") or ""),
                        decision_reason=(
                            f"任务 {_task.get('id')} 分配 {_task.get('agent')} "
                            f"(角色 {_task.get('required_role') or '?'})"
                        ),
                    )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        ids = [str(t.get("id") or "") for t in plan_tasks]
        graph = TaskDependencyGraph.load(dependencies_file)
        if all(ids):
            order = graph.topological_order(ids)
            pos = {tid: i for i, tid in enumerate(order)}
            plan_tasks = sorted(plan_tasks, key=lambda t: pos.get(str(t.get("id")), 0))
        # S10-057 §P2: 后继任务映射 (依赖图 → task_id → [依赖它的任务], Handoff 输入)
        tasks_by_id = {str(t.get("id") or ""): t for t in plan_tasks if t.get("id")}
        successors: dict[str, list[str]] = {}
        dependencies: dict[str, list[str]] = {}
        for task in plan_tasks:
            tid = str(task.get("id") or "")
            if not tid:
                continue
            deps = [d for d in graph.get(tid) if d in tasks_by_id]
            dependencies[tid] = deps
            for dep in deps:
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
        # S10-059 P4: 决策引擎 (项目级 handoff_decisions.json — 决策可解释性资产)
        decision_engine = HandoffDecisionEngine(
            file=project_dir / HandoffDecisionEngine.FILE_NAME
        )
        return plan_tasks, TeamRunContext(
            team=team,
            detector=detector,
            store=store,
            successors=successors,
            tasks_by_id=tasks_by_id,
            handoff_store=handoff_store,
            decision_engine=decision_engine,
            dependencies=dependencies,
            agent_roles=member_roles,
        )

    def _parallel_prepare(
        self,
        project_dir: Path,
        slug: str,
        plan_tasks: list[dict[str, Any]],
        *,
        max_concurrency: int,
        schedule_file: Optional[Path],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """M3c parallel 模式准备 (S10-090 M3-3): plan.json → rounds → 队列重排。

        ① 读 plan.json (M3b 关键路径标注产物: tasks/edges/critical_path/order);
           缺失/损坏/无任务 → 视为无 plan (走降级路径);
        ② TaskScheduler.schedule(plan, state, max_concurrency) — 就绪队列 +
           同文件冲突串行化 (ConflictResolver 复用, 不修改核心) + 并发分桶;
        ③ 按 rounds 扁平序重排 execution_plan 任务 (同轮内保持原相对序);
           未出现在 rounds 的任务 (execution_plan 与 plan.json id 不一致时)
           → 追加在队尾保持原顺序 (诚实: 未调度任务不伪造并行);
        ④ 落盘 schedule.json (调度器内部, 可审计) + 返回审计视图
           {rounds, max_concurrency, degraded, reason, schedule_file}。
        失败安全: 任何异常 → 降级顺序执行 (原队列 + degraded 标注, 不抛)。
        """
        from .conflicts import ConflictResolver
        from .scheduler import TaskScheduler

        sched_file = (
            Path(schedule_file) if schedule_file is not None else project_dir / "schedule.json"
        )
        m3b_plan: Optional[dict[str, Any]] = None
        plan_path = project_dir / "plan.json"
        if plan_path.is_file():
            try:
                loaded = json.loads(plan_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("tasks"):
                    m3b_plan = loaded
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 无 plan 降级
                m3b_plan = None
        resolver = ConflictResolver(resolution_file=project_dir / "conflict_resolution.json")
        try:
            sched = TaskScheduler(workspace=self.workspace)
            result = sched.schedule(
                m3b_plan,
                {
                    "completed": [],
                    "project_dir": str(project_dir),
                    "schedule_file": str(sched_file),
                },
                max_concurrency=max_concurrency,
                conflict_resolver=resolver,
                persist=True,
            )
        except Exception:  # noqa: BLE001 — 失败安全: 调度异常 → 降级顺序执行
            result = None
        by_id = {str(t.get("id") or ""): t for t in plan_tasks}
        if result is not None and result.order:
            ordered = [by_id[tid] for tid in result.order if tid in by_id]
            seen = {str(t.get("id") or "") for t in ordered}
            ordered += [t for t in plan_tasks if str(t.get("id") or "") not in seen]
            if ordered:
                plan_tasks = ordered
        view = {
            "rounds": [list(r) for r in (result.rounds if result is not None else [])],
            "max_concurrency": max_concurrency,
            "degraded": bool(result.degraded) if result is not None else True,
            "reason": (
                result.degradation_reason
                if result is not None and result.degraded
                else ("调度器异常 — 降级顺序执行" if result is None else "正常并行调度")
            ),
            "schedule_file": str(sched_file),
        }
        return plan_tasks, view

    # ------------------------------------------------------------ M3e 全链执行 (S10-097)

    def _m3_emit(
        self,
        project_dir: Path,
        event_type: str,
        *,
        task_id: str = "",
        agent_id: str = "",
        **fields: Any,
    ) -> None:
        """M3 审计事件发射 (失败安全: 审计故障不中断 M3 链)。"""
        try:
            from ..audit.audit_emitter import AuditEmitter

            AuditEmitter(workspace=project_dir.parent.parent).emit(
                event_type,
                project_id=project_dir.name,
                task_id=task_id,
                agent_id=agent_id,
                **fields,
            )
        except Exception:  # noqa: BLE001 — 失败安全铁律
            pass

    def _m3_plan(
        self,
        project_dir: Path,
        slug: str,
        *,
        max_concurrency: int,
    ) -> Optional[dict[str, Any]]:
        """M3 计划链 (M3a→M3b→M3c): 复合任务 → 原子叶子 → 关键路径 → 轮次。

        ① plan.json (M3b 产物) 已存在且含任务 → 直接复用 (输入契约);
        ② 缺失 → DecomposeEngine.decompose (落盘 decomposition.json) →
           CriticalPathEngine.compute (落盘 plan.json/dependencies.json);
        ③ TaskScheduler.schedule — 依赖就绪轮次 + 同文件冲突 ConflictResolver
           串行化 (M3c 复用, 不修改核心) → rounds/order (落盘 schedule.json)。
        失败安全: 任何异常/无任务 → 返回 None (由调用方降级 solo, 诚实标注)。
        """
        from .conflicts import ConflictResolver
        from .critical_path import CriticalPathEngine
        from .decomposer import DecomposeEngine
        from .scheduler import TaskScheduler

        plan: Optional[dict[str, Any]] = None
        plan_path = project_dir / "plan.json"
        if plan_path.is_file():
            try:
                loaded = json.loads(plan_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("tasks"):
                    plan = loaded
            except Exception:  # noqa: BLE001 — 损坏 → 走全链生成
                plan = None
        if plan is None:
            # M3a: 产品 → 复合根任务 → 原子叶子
            product: dict[str, Any] = {}
            product_path = project_dir / "product.json"
            if product_path.is_file():
                try:
                    loaded = json.loads(product_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        product = loaded
                except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 空产品
                    product = {}
            name = str(product.get("name") or slug)
            features = [str(f) for f in (product.get("core_features") or [])]
            root_task = {
                "id": "root",
                "name": name,
                "goal": str(product.get("problem") or f"实现产品: {name}"),
                "requirement": (
                    ("实现产品全部核心功能: " + "、".join(features))
                    if features
                    else f"实现产品: {name}"
                ),
            }
            eng = DecomposeEngine(workspace=self.workspace, project_id=slug)
            dres = eng.decompose(root_task, product=product)
            if dres.error or not dres.leaves:
                return None  # 诚实降级: 无原子叶子
            # M3b: 关键路径 (落盘 plan.json/dependencies.json)
            ceng = CriticalPathEngine(workspace=self.workspace, project_id=slug)
            cres = ceng.compute(dres.leaves)
            if not cres.tasks:
                return None
            plan = {
                "project_id": slug,
                "tasks": cres.tasks,
                "edges": cres.edges,
                "critical_path": cres.critical_path,
                "order": cres.order,
            }
        # M3c: 调度轮次 (依赖就绪 + 冲突串行, ConflictResolver 复用)
        resolver = ConflictResolver(resolution_file=project_dir / "conflict_resolution.json")
        sched = TaskScheduler(workspace=self.workspace)
        sres = sched.schedule(
            plan,
            {"completed": [], "project_dir": str(project_dir)},
            max_concurrency=max_concurrency,
            conflict_resolver=resolver,
            persist=True,
        )
        if not sres.order:
            return None  # 诚实降级: 无任务可调度
        return {
            "tasks": [dict(t) for t in (plan.get("tasks") or [])],
            "rounds": [list(r) for r in sres.rounds],
            "order": list(sres.order),
            "degraded": bool(sres.degraded),
            "degradation_reason": str(sres.degradation_reason or ""),
            "conflicts": [dict(c) for c in sres.conflicts],
        }

    def _execute_m3(
        self,
        project_dir: Path,
        slug: str,
        state: ExecutionState,
        fallback_tasks: list[dict[str, Any]],
        *,
        execute_fn: Optional[ExecuteFn],
        max_retry: int,
        agents_file: Optional[Path],
        max_concurrency: int,
        run_solo: Callable[[], ExecutionResult],
    ) -> ExecutionResult:
        """M3 全链执行入口 (S10-097): 计划链 → 轮次动态分配执行 → 证据/审计。

        失败安全: 计划链/执行链任何异常 → 降级 solo 顺序执行 (run_solo,
        EXECUTION_M3_DEGRADED + state.m3.degraded=True 诚实标注); 单任务失败
        不中断整链 (标记 failed, 后续轮次继续)。
        """
        try:
            m3 = self._m3_plan(project_dir, slug, max_concurrency=max_concurrency)
        except Exception as exc:  # noqa: BLE001 — 失败安全: M3 链异常 → 降级 solo
            return self._m3_degrade(
                project_dir,
                slug,
                state,
                fallback_tasks,
                run_solo,
                reason=f"M3 计划链异常 — 降级 solo 顺序执行: {exc}",
            )
        if m3 is None:
            return self._m3_degrade(
                project_dir,
                slug,
                state,
                fallback_tasks,
                run_solo,
                reason="M3 计划链无可用任务 — 降级 solo 顺序执行",
            )
        try:
            return self._m3_execute_rounds(
                project_dir,
                slug,
                state,
                m3,
                execute_fn=execute_fn,
                max_retry=max_retry,
                agents_file=agents_file,
            )
        except Exception as exc:  # noqa: BLE001 — 失败安全: 执行链异常 → 降级 solo
            return self._m3_degrade(
                project_dir,
                slug,
                state,
                fallback_tasks,
                run_solo,
                reason=f"M3 执行链异常 — 降级 solo 顺序执行: {exc}",
            )

    def _m3_degrade(
        self,
        project_dir: Path,
        slug: str,
        state: ExecutionState,
        fallback_tasks: list[dict[str, Any]],
        run_solo: Callable[[], ExecutionResult],
        *,
        reason: str,
    ) -> ExecutionResult:
        """M3 链异常 → 降级 solo 顺序执行 (诚实标注 degraded, 不伪造 M3 执行)。"""
        state.tasks = [self._task_record(t) for t in fallback_tasks]
        state.m3 = {
            "rounds": [],
            "assignments": [],
            "evidence": [],
            "degraded": True,
            "reason": str(reason),
        }
        self._save_state(project_dir, state)
        # EXECUTION_M3_DEGRADED 审计 (诚实标注降级)
        self._m3_emit(
            project_dir,
            "EXECUTION_M3_DEGRADED",
            decision_reason=str(reason),
            result={"degraded": True, "fallback": "solo"},
        )
        return run_solo()

    def _m3_evidence(
        self,
        project_dir: Path,
        slug: str,
        task: dict[str, Any],
        outcome: dict[str, Any],
        validation: ValidationResult,
    ) -> Optional[dict[str, str]]:
        """每任务 EvidenceBundle 落盘 (M1a 复用 EvidenceBuilder/EvidenceStore +
        EVIDENCE_BUNDLE_CREATED 审计)。失败安全: 证据故障不中断执行链。"""
        try:
            from .evidence import (
                EvidenceBuilder,
                EvidenceStore,
                emit_evidence_created,
            )

            task_id = str(task.get("id") or "")
            diff = str(outcome.get("diff") or "")
            artifact_path = str(task.get("artifact") or "")
            if not diff and artifact_path and Path(artifact_path).is_file():
                try:
                    diff = Path(artifact_path).read_text(encoding="utf-8")
                except Exception:  # noqa: BLE001 — 读取失败 → 空 diff
                    diff = ""
            logs: list[dict[str, Any]] = []
            logs.append(
                EvidenceBuilder._step_log(
                    "execute",
                    f"任务 {task_id} 执行完成: {task.get('status')}",
                    detail=str(task.get("error") or ""),
                )
            )
            if validation is not None:
                logs.append(
                    EvidenceBuilder._step_log(
                        "validation",
                        "验证通过" if validation.success else "验证失败",
                        detail="; ".join(validation.errors) if validation.errors else "",
                    )
                )
            test_results = [
                {
                    "ok": bool(validation.success),
                    "output": (
                        f"tests {getattr(validation, 'tests_total', 0)} "
                        f"passed {getattr(validation, 'tests_passed', 0)} "
                        f"failed {getattr(validation, 'tests_failed', 0)}"
                    ),
                }
            ]
            decisions = [
                {"step": "assign", "reason": str(task.get("reason") or "")},
                {"step": "execute", "reason": f"任务 {task_id} 状态 {task.get('status')}"},
            ]
            bundle = EvidenceBuilder.build(
                project_id=slug,
                task_id=task_id,
                agent_id=str(task.get("agent") or ""),
                diff=diff,
                test_results=test_results,
                logs=logs,
                decisions=decisions,
                artifacts=[artifact_path] if artifact_path else [],
            )
            path = EvidenceStore(self.workspace, slug).save(bundle)
            emit_evidence_created(self.workspace, bundle)
            return {
                "task_id": task_id,
                "bundle_id": bundle.bundle_id,
                "path": str(path),
            }
        except Exception:  # noqa: BLE001 — 证据故障不中断执行链
            return None

    def _m3_execute_rounds(
        self,
        project_dir: Path,
        slug: str,
        state: ExecutionState,
        m3: dict[str, Any],
        *,
        execute_fn: Optional[ExecuteFn],
        max_retry: int,
        agents_file: Optional[Path],
    ) -> ExecutionResult:
        """轮次执行 (M3e): 每轮 EXECUTION_ROUND_STARTED → 任务 AgentMatcher 动态
        分配 (M3-4) → 执行 → 证据落盘 → EXECUTION_TASK_COMPLETED → 轮结束审计
        → 下一轮 (依赖就绪由调度轮次保证)。单任务失败不中断整链; 输出同
        execute_project 既有结果结构 + state.m3 = {rounds, assignments, evidence}。
        """
        runner: ExecuteFn = execute_fn if execute_fn is not None else _default_execute_fn
        # M3-4 动态分配: AgentMatcher 实时匹配 (skill × 历史成功率) — 复用不修改
        registry = AgentRegistry.load(agents_file)
        records_file = self.workspace / "exec" / "execution_records.json"
        metrics = (
            AgentMetrics.load_from_records(records_file)
            if records_file.is_file()
            else {}
        )
        matcher = AgentMatcher(registry=registry, metrics=metrics)

        # state.tasks ← 调度任务 (M3 计划产物; 全新执行全 pending)
        plan_tasks = [dict(t) for t in (m3.get("tasks") or [])]
        state.tasks = [self._task_record(t) for t in plan_tasks]
        state.m3 = {
            "rounds": [list(r) for r in (m3.get("rounds") or [])],
            "assignments": [],
            "evidence": [],
        }
        if m3.get("degraded"):
            state.m3["degraded"] = True
            state.m3["reason"] = str(m3.get("degradation_reason") or "调度降级")
        self._save_state(project_dir, state)

        completed = failed = 0
        artifacts: list[str] = []
        errors: list[str] = []
        costs: list[str] = []
        validations: list[ValidationResult] = []
        state_by_id = {str(t.get("id") or ""): t for t in state.tasks}
        for rindex, round_ids in enumerate(m3.get("rounds") or [], start=1):
            round_tasks = [state_by_id[tid] for tid in round_ids if tid in state_by_id]
            self._m3_emit(
                project_dir,
                "EXECUTION_ROUND_STARTED",
                result={"round": rindex, "tasks": list(round_ids)},
            )
            for task in round_tasks:
                task_id = str(task.get("id") or "")
                # M3-4: AgentMatcher 实时动态分配 (skill × 历史成功率 × 成本)
                match = matcher.match(task, registry=registry, metrics=metrics)
                agent_id = str(match.get("agent") or "")
                assignment = {
                    "round": rindex,
                    "task": task_id,
                    "agent_id": agent_id,
                    "matched": bool(agent_id),
                    "reason": str(match.get("reason") or ""),
                }
                state.m3["assignments"].append(assignment)
                task["agent"] = agent_id
                task["matched"] = bool(agent_id)
                task["reason"] = assignment["reason"]
                self._save_state(project_dir, state)
                self._m3_emit(
                    project_dir,
                    "EXECUTION_TASK_ASSIGNED",
                    task_id=task_id,
                    agent_id=agent_id,
                    decision_reason=(
                        f"第{rindex}轮任务 {task_id} 分配 agent={agent_id or '无匹配'}: "
                        + (assignment["reason"] or "")
                    ),
                    result={"round": rindex, "matched": bool(agent_id)},
                )
                # 执行 (复用 _execute_with_retry — 真实执行 + retry + patch delivery)
                outcome = self._execute_with_retry(
                    project_dir, state, task, runner, max_retry
                )
                # 质量门 (复用 Validator — 同 solo/team 口径)
                validation = self.validator.validate(task, outcome)
                task["validation"] = "passed" if validation.success else "failed"
                validations.append(validation)
                self._save_state(project_dir, state)
                # 证据落盘 (M1a 复用: EvidenceBundle → evidence/<bundle>.json)
                evidence_ref = self._m3_evidence(
                    project_dir, slug, task, outcome, validation
                )
                if evidence_ref is not None:
                    state.m3["evidence"].append(evidence_ref)
                    self._save_state(project_dir, state)
                if task.get("status") == "completed" and validation.success:
                    completed += 1
                    if task.get("artifact"):
                        artifacts.append(str(task["artifact"]))
                else:
                    failed += 1
                    if task.get("status") == "completed":
                        # 执行成功但验证失败 → 同 solo 口径标记 failed
                        task["status"] = "failed"
                        task["error"] = "; ".join(validation.errors) or "验证失败"
                        self._save_state(project_dir, state)
                    reason = str(
                        task.get("error")
                        or "; ".join(validation.errors)
                        or "任务执行失败"
                    )
                    errors.append(f"{task_id}: {reason}")
                    # 失败 → repair_task.json (同 _run_queue 失败处理口径)
                    RepairManager.create_repair(
                        project_dir,
                        task,
                        reason,
                        retry_count=int(task.get("retry_count") or 0),
                    )
                if isinstance(outcome, dict) and outcome.get("cost"):
                    costs.append(str(outcome["cost"]))
                self._m3_emit(
                    project_dir,
                    "EXECUTION_TASK_COMPLETED",
                    task_id=task_id,
                    agent_id=agent_id,
                    decision_reason=f"第{rindex}轮任务 {task_id} 完成",
                    result={
                        "round": rindex,
                        "status": str(task.get("status") or ""),
                        "validation": str(task.get("validation") or ""),
                        "bundle_id": (
                            str(evidence_ref.get("bundle_id") or "")
                            if evidence_ref is not None
                            else ""
                        ),
                    },
                )
            self._m3_emit(
                project_dir,
                "EXECUTION_ROUND_COMPLETED",
                result={
                    "round": rindex,
                    "tasks": list(round_ids),
                    "completed": sum(
                        1 for t in round_tasks if t.get("status") == "completed"
                    ),
                    "failed": sum(
                        1 for t in round_tasks if t.get("status") == "failed"
                    ),
                },
            )
        # 结果汇总 + Lifecycle (同 _run_queue 终态口径)
        result = ExecutionResult(
            project=slug,
            status=Lifecycle.USER_ACCEPTANCE if failed == 0 else "failed",
            completed_tasks=completed,
            failed_tasks=failed,
            artifacts=artifacts,
            cost=" · ".join(costs),
            errors=errors,
        )
        if failed == 0:
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
        # 验证汇总资产化 (同 _run_queue 口径)
        summary = ValidationResult(
            success=failed == 0,
            tests_total=len(validations),
            tests_passed=sum(1 for v in validations if v.success),
            tests_failed=sum(1 for v in validations if not v.success),
            errors=[
                f"{t.get('id') or t.get('name')}: {err}"
                for t, v in zip(state.tasks, validations)
                for err in (v.errors if not v.success else [])
            ],
        )
        self.validator.save(project_dir, slug, summary)
        self._m3_emit(
            project_dir,
            "TEST_PASSED" if failed == 0 else "TEST_FAILED",
            actor_type="system",
            actor_id="validator",
            decision_reason=(
                f"M3 测试验证通过: {summary.tests_passed}/{summary.tests_total}"
                if failed == 0
                else f"M3 测试验证失败: {summary.tests_failed}/{summary.tests_total}"
            ),
            result={
                "tests_total": summary.tests_total,
                "tests_passed": summary.tests_passed,
                "tests_failed": summary.tests_failed,
            },
        )
        self._m3_emit(
            project_dir,
            "TASK_COMPLETED" if failed == 0 else "TASK_FAILED",
            actor_type="system",
            actor_id="orchestrator",
            decision_reason=(
                f"M3 生产执行完成: {len(state.tasks)} 任务, "
                f"{sum(1 for t in state.tasks if t.get('status') == 'completed')} 完成"
                if failed == 0
                else f"M3 生产执行有失败: {failed} 任务失败"
            ),
            result={"failed": failed, "total": len(state.tasks)},
        )
        # S10-071 P0-3: Memory 自动沉淀 (同 _run_queue 口径, 失败安全)
        try:
            from ..memory.auto_learn import AutoLearner

            AutoLearner().learn_from_workspace(project_dir.parent.parent)
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        # M1b T3: 执行完成证据包 (同普通执行口径, 失败安全)
        self._attach_execution_evidence(project_dir, slug, result, state, validations)
        return result

    def resume(
        self,
        project_id: str,
        *,
        execute_fn: Optional[ExecuteFn] = None,
        max_retry: int = DEFAULT_MAX_RETRY,
        # S10-060: 重规划接入 (同 execute_project — 恢复执行也支持自主重规划)
        replanner: Optional[ReplanningEngine] = None,
        max_replan: int = 5,
        insert_tasks: Optional[list[dict[str, Any]]] = None,
        dependencies_file: Optional[Path] = None,
        replanning_file: Optional[Path] = None,
        # S10-061 批次 B: 自动缺口分析接入 (同 execute_project)
        gap_analyzer: Optional[GapAnalyzer] = None,
        task_proposal: Optional[TaskProposalEngine] = None,
        task_validator: Optional[TaskProposalValidator] = None,
        max_auto_insert_tasks: int = 5,
        max_tasks_per_round: int = 3,
        max_total_generated_tasks: int = 10,
        auto_mode: str = "auto_execute",
        proposals_file: Optional[Path] = None,
        # S10-062 批次 C: planning_mode + LLM planning 接入 (同 execute_project;
        # 恢复执行不重跑 PlanCritic 执行前检查 — 防重复插入)
        planning_mode: str = PLANNING_MODE_HYBRID,
        llm_reasoning: Optional[ReasoningProvider] = None,
        llm_gap_analyzer: Optional[LLMGapAnalyzer] = None,
        llm_task_proposal: Optional[LLMTaskProposalEngine] = None,
        llm_trace: Optional[PlanningTrace] = None,
        llm_confidence_threshold: float = 0.5,
    ) -> ExecutionResult:
        """恢复执行 (设计 §3): 从 execution_state.json 继续 pending/failed 任务。

        跳过 completed; failed 任务重置 retry_count 重新执行 (仍受 max_retry 约束);
        无待恢复任务 → 直接汇总 (不重跑)。
        S10-060: skipped/blocked/split (计划级决策产物) 不重跑 (resume 语义保留)。
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
        # S10-060: 重规划引擎解析 (replanning_file 便捷参数 → 引擎构造; 缺省关闭)
        if replanner is None and replanning_file is not None:
            replanner = ReplanningEngine(file=replanning_file)
        # S10-061 批次 B: 自动提案组件解析 (同 execute_project — 缺省真实引擎)
        if gap_analyzer is not None:
            task_proposal = task_proposal if task_proposal is not None else TaskProposalEngine()
            task_validator = (
                task_validator
                if task_validator is not None
                else TaskProposalValidator()
            )
        # S10-062 批次 C: LLM planning 组件装配 (同 execute_project)
        llm_gap_analyzer, llm_task_proposal, _planning_mode = (
            self._assemble_llm_planning(
                planning_mode,
                llm_reasoning,
                llm_gap_analyzer,
                llm_task_proposal,
                llm_trace,
                llm_confidence_threshold,
            )
        )
        plan = self._load_plan(project_dir) if replanner is not None else None
        result = self._run_queue(
            project_dir,
            slug,
            state,
            execute_fn=execute_fn,
            max_retry=max_retry,
            plan=plan,
            replanner=replanner,
            max_replan=int(max_replan or 5),
            insert_tasks=list(insert_tasks or []),
            dependencies_file=dependencies_file,
            gap_analyzer=gap_analyzer,
            task_proposal=task_proposal,
            task_validator=task_validator,
            max_auto_insert_tasks=int(max_auto_insert_tasks or 5),
            max_tasks_per_round=int(max_tasks_per_round or 3),
            max_total_generated_tasks=int(max_total_generated_tasks or 10),
            auto_mode=str(auto_mode or "auto_execute"),
            proposals_file=proposals_file,
            planning_mode=_planning_mode,
            llm_gap_analyzer=llm_gap_analyzer,
            llm_task_proposal=llm_task_proposal,
            llm_reasoning=llm_reasoning,
            llm_trace=llm_trace,
            llm_confidence_threshold=float(llm_confidence_threshold or 0.5),
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
        # S10-071 P0-4: 交付事件自动 Audit (失败安全)
        try:
            from ..audit.audit_emitter import AuditEmitter
            AuditEmitter(workspace=project_dir.parent.parent).emit(
                "PROJECT_DELIVERED", project_id=slug,
                actor_type="user", actor_id=str(getattr(self, "user", "") or ""),
                decision_reason=f"用户验收通过, 项目 {slug} 交付",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
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
        plan: Optional[dict[str, Any]] = None,
        replanner: Optional[ReplanningEngine] = None,
        max_replan: int = 5,
        insert_tasks: Optional[list[dict[str, Any]]] = None,
        dependencies_file: Optional[Path] = None,
        # S10-061 批次 B: 自动缺口分析 + 提案接入 (透传 _replan_on_failure)
        gap_analyzer: Optional[GapAnalyzer] = None,
        task_proposal: Optional[TaskProposalEngine] = None,
        task_validator: Optional[TaskProposalValidator] = None,
        max_auto_insert_tasks: int = 5,
        max_tasks_per_round: int = 3,
        max_total_generated_tasks: int = 10,
        auto_mode: str = "auto_execute",
        proposals_file: Optional[Path] = None,
        # S10-062 批次 C: planning_mode + LLM planning (透传 _replan_on_failure)
        planning_mode: str = PLANNING_MODE_HYBRID,
        llm_gap_analyzer: Optional[LLMGapAnalyzer] = None,
        llm_task_proposal: Optional[LLMTaskProposalEngine] = None,
        llm_reasoning: Optional[ReasoningProvider] = None,
        llm_trace: Optional[PlanningTrace] = None,
        llm_confidence_threshold: float = 0.5,
        # S10-063 批次 B: 治理上下文 (budget/cost_ledger/review_gate/policy/
        # loop_guard 聚合; None → 无治理行为, 现有行为零变化)
        governance: Optional[_GovernanceContext] = None,
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
        blocked_stop = False  # S10-059: 任务被 BLOCK (锁未释放) → 暂缓 (可 resume 继续)
        review_stop = False  # S10-060: 重规划超限 → REQUEST_REVIEW → 停止 (需人工评审)
        governance_stop = False  # S10-063: 治理停止 (budget/policy/loop_guard/review)
        governance_stop_status = ""  # S10-063: "blocked" | "waiting_for_review"
        governance_stop_reason = ""  # S10-063: 停止原因 (可解释)
        idx = 0
        while idx < len(state.tasks):
            task = state.tasks[idx]
            idx += 1
            status = str(task.get("status") or "")
            if status == "completed":
                # 已完成任务跳过 (resume 语义: 不重跑); 缺 validation 字段 → 默认 passed
                task.setdefault("validation", "passed")
                completed += 1
                if task.get("artifact"):
                    artifacts.append(str(task["artifact"]))
                continue
            if status in ("skipped", "blocked", "split"):
                # S10-060: 计划级决策产物 (SKIP_TASK/BLOCK_TASK/SPLIT_TASK) —
                # 不再执行 (决策已记录 replanning_decisions.json, 可解释; resume 不重跑)
                continue
            if team_run is not None:
                # S10-056 批次 B + S10-059: 团队模式冲突检测 + 自主决策 + 文件锁
                # (SERIALIZE/BLOCK → acquire; 锁未释放 → BLOCK 暂缓)
                team_run.before_task(project_dir, task)
                # S10-057 §P1: 暂停检查 — 已暂停 → 停止队列 (剩余任务保持 pending)
                if team_run.is_paused(project_dir):
                    paused_stop = True
                    break
                # S10-059: 锁未释放 (前序任务未完成/未释放) → 本任务暂缓不执行
                # (BLOCK 决策已记录, 不无限等待; resume 后可继续)
                if team_run.is_blocked():
                    blocked_stop = True
                    continue
                # S10-057 §P3: Workspace Context 注入 → task["context"] 透传
                team_run.inject_context(project_dir, task)
                # S10-057 §P1: TeamExecutionState 任务级 running
                team_run.update_team_state(project_dir, task, "running")
            # S10-063: 治理预检 — 任务执行前 budget enforce("execute") + policy
            # can_execute (block/review → 停止队列; warn → 记录继续)
            # S10-065: 执行时间闸优先 — elapsed >= max_execution_time → 停止
            # (慢执行不再无限跑; 同 budget enforce 语义 blocked/waiting_for_review)
            if governance is not None:
                stop = (
                    governance.check_execution_time()
                    or governance.check_budget("execute", task)
                    or governance.check_policy("execute", task)
                )
                if stop:
                    governance_stop = True
                    governance_stop_status = str(stop.get("status") or "blocked")
                    governance_stop_reason = str(stop.get("reason") or "")
                    break
            outcome = self._execute_with_retry(
                project_dir, state, task, runner, max_retry, governance=governance
            )
            # S10-063: 重试闸门停止 (budget retry / policy can_retry) — 停止队列
            if governance is not None and governance.stop_status:
                governance_stop = True
                governance_stop_status = governance.stop_status
                governance_stop_reason = governance.stop_reason
                break
            # S10-063: 任务执行后成本记录 (EXECUTION — 设计 §4)
            if governance is not None:
                governance.record_execution(task, outcome)
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
                # S10-063: 失败后治理 — loop_guard 组合总闸 (same_failure →
                # block/review 停止) + budget repair + policy can_repair
                if governance is not None:
                    stop = governance.check_loop_failure(task, reason)
                    if stop:
                        governance_stop = True
                        governance_stop_status = str(stop.get("status") or "blocked")
                        governance_stop_reason = str(stop.get("reason") or "")
                        break
                    stop = governance.check_budget("repair", task) or governance.check_policy(
                        "repair", task
                    )
                    if stop:
                        governance_stop = True
                        governance_stop_status = str(stop.get("status") or "blocked")
                        governance_stop_reason = str(stop.get("reason") or "")
                        break
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
                # S10-060 §P5: 计划级重规划 — 任务失败 → 观察 (agent_output/
                # validation) → ReplanningEngine.decide → 应用 (改 DAG/Plan)
                # → 继续执行 (非简单 retry; Repair 任务级路径不变)
                if replanner is not None:
                    # S10-063: 重规划前治理 — budget enforce("replan") + policy
                    # can_replan (block/review → 停止队列)
                    if governance is not None:
                        stop = governance.check_budget("replan", task) or governance.check_policy(
                            "replan", task
                        )
                        if stop:
                            governance_stop = True
                            governance_stop_status = str(stop.get("status") or "blocked")
                            governance_stop_reason = str(stop.get("reason") or "")
                            break
                    signal = self._replan_on_failure(
                        project_dir,
                        state,
                        plan,
                        task,
                        outcome,
                        validation,
                        replanner=replanner,
                        max_replan=max_replan,
                        insert_tasks=insert_tasks,
                        dependencies_file=dependencies_file,
                        team_run=team_run,
                        gap_analyzer=gap_analyzer,
                        task_proposal=task_proposal,
                        task_validator=task_validator,
                        max_auto_insert_tasks=max_auto_insert_tasks,
                        max_tasks_per_round=max_tasks_per_round,
                        max_total_generated_tasks=max_total_generated_tasks,
                        auto_mode=auto_mode,
                        proposals_file=proposals_file,
                        planning_mode=planning_mode,
                        llm_gap_analyzer=llm_gap_analyzer,
                        llm_task_proposal=llm_task_proposal,
                        llm_reasoning=llm_reasoning,
                        llm_trace=llm_trace,
                        llm_confidence_threshold=llm_confidence_threshold,
                        governance=governance,
                    )
                    if signal == "review":
                        # 重规划超限 → 停止队列 (需人工评审; resume 可继续)
                        review_stop = True
                        break
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
            and not blocked_stop
            and not review_stop
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
                else (
                    "blocked"
                    if blocked_stop and failed == 0
                    else (
                        "review_required"
                        if review_stop
                        else (
                            # S10-063: 治理停止 (budget block/review)
                            governance_stop_status
                            if governance_stop
                            else (Lifecycle.USER_ACCEPTANCE if failed == 0 else "failed")
                        )
                    )
                )
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
        # 团队暂停/锁阻塞停止 (部分完成) → 保持 DEVELOPMENT (可 resume 继续)。
        # DELIVERED 仅经 accept_project 用户确认后到达 (验收 E/G)。
        # S10-063: governance_stop (budget block/review) → 保持 DEVELOPMENT
        # + governance_status 落盘 (可解释: 为什么停止)。
        if failed == 0 and not paused_stop and not blocked_stop and not review_stop and not governance_stop:
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
            # S10-063: 治理停止信息落盘 (可解释: 为什么停止)
            if governance_stop:
                state.governance_status = governance_stop_status
                state.governance_reason = governance_stop_reason
                errors.append(f"governance:{governance_stop_status} — {governance_stop_reason}")
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
        # S10-073 P0-B: 测试结果自动 Audit (TEST_PASSED/FAILED, 失败安全)
        try:
            from ..audit.audit_emitter import AuditEmitter
            AuditEmitter(workspace=project_dir.parent.parent).emit(
                "TEST_PASSED" if failed == 0 else "TEST_FAILED",
                project_id=slug, actor_type="system", actor_id="validator",
                decision_reason=(
                    f"测试验证通过: {summary.tests_passed}/{summary.tests_total}"
                    if failed == 0 else f"测试验证失败: {summary.tests_failed}/{summary.tests_total}"
                ),
                result={"tests_total": summary.tests_total, "tests_passed": summary.tests_passed,
                        "tests_failed": summary.tests_failed},
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        # S10-071 P0-4: Audit 自动接入生产链 (执行完成事件, 失败安全)
        try:
            from ..audit.audit_emitter import AuditEmitter
            AuditEmitter(workspace=project_dir.parent.parent).emit(
                "TASK_COMPLETED" if failed == 0 else "TASK_FAILED",
                project_id=slug, actor_type="system", actor_id="orchestrator",
                decision_reason=(
                    f"生产执行完成: {len(state.tasks)} 任务, "
                    f"{sum(1 for t in state.tasks if t.get('status') == 'completed')} 完成"
                    if failed == 0 else f"生产执行有失败: {failed} 任务失败"
                ),
                result={"failed": failed, "total": len(state.tasks)},
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        # S10-071 P0-3: Memory 自动沉淀 (生产结束自动学习, 失败安全)
        try:
            from ..memory.auto_learn import AutoLearner
            AutoLearner().learn_from_workspace(project_dir.parent.parent)
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        if team_run is not None:
            # S10-057 §P1: 团队状态终态落盘 (completed/paused/failed + validation 记录)
            team_state = TeamExecutionState.get(project_dir)
            team_state["status"] = (
                "completed"
                if failed == 0 and not paused_stop and not blocked_stop and not review_stop
                else (
                    "paused"
                    if paused_stop
                    else (
                        "blocked"
                        if blocked_stop
                        else ("review_required" if review_stop else "failed")
                    )
                )
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
        # M1b T3: 普通执行 (execute_project/resume) 完成后自动组装证据包 —
        # 复用 EvidenceBuilder.from_execution_result (失败安全, 不阻断执行)
        self._attach_execution_evidence(project_dir, slug, result, state, validations)
        return result

    # ------------------------------------------------------------- M1b T3: 证据包接入普通执行

    def _attach_execution_evidence(
        self,
        project_dir: Path,
        slug: str,
        result: ExecutionResult,
        state: ExecutionState,
        validations: list,
    ) -> None:
        """普通执行 (execute_project/resume) 完成后自动组装证据包 (失败安全)。

        复用 EvidenceBuilder.from_execution_result (M1a from_repo_result 模式):
        测试结果 + 决策链 + 产物清单 + 执行日志 (T4 执行事件摘要 — 任务队列/
        验证/终态)。普通执行无 unified patch → diff 留空 (不伪造)。
        落盘 projects/<slug>/evidence/ + EVIDENCE_BUNDLE_CREATED 审计;
        任何异常静默 (证据包失败不阻断执行链)。
        """
        try:
            from .evidence import (
                EvidenceBuilder,
                EvidenceStore,
                emit_evidence_created,
            )

            logs: list[dict[str, Any]] = []
            done = sum(1 for t in state.tasks if t.get("status") == "completed")
            logs.append(
                EvidenceBuilder._step_log(
                    "execute",
                    f"任务队列执行完成: {done}/{len(state.tasks)} 任务完成",
                )
            )
            for t in state.tasks:
                logs.append(
                    EvidenceBuilder._step_log(
                        f"task:{t.get('id') or t.get('name') or '?'}",
                        str(t.get("status") or "?"),
                        detail=str(t.get("error") or ""),
                    )
                )
            if validations:
                ok = sum(1 for v in validations if getattr(v, "success", False))
                logs.append(
                    EvidenceBuilder._step_log(
                        "validation", f"验证 {ok}/{len(validations)} 通过"
                    )
                )
            test_results = [
                {
                    "ok": bool(getattr(v, "success", False)),
                    "output": (
                        f"tests {getattr(v, 'tests_total', 0)} "
                        f"passed {getattr(v, 'tests_passed', 0)} "
                        f"failed {getattr(v, 'tests_failed', 0)}"
                    ),
                }
                for v in validations
            ]
            if not test_results:
                test_results = [{
                    "ok": result.failed_tasks == 0,
                    "output": (
                        f"{result.completed_tasks} completed / "
                        f"{result.failed_tasks} failed"
                    ),
                }]
            reasons = [f"项目 {slug} 执行: {result.completed_tasks} 完成 / "
                       f"{result.failed_tasks} 失败"]
            if result.errors:
                reasons.append("错误: " + "; ".join(result.errors))
            decisions = [{"step": "execute", "reason": " ".join(reasons)}]
            bundle = EvidenceBuilder.from_execution_result(
                result,
                project_id=slug,
                agent_id="orchestrator",
                logs=logs,
                test_results=test_results,
                decisions=decisions,
            )
            EvidenceStore(project_dir.parent.parent, slug).save(bundle)
            emit_evidence_created(project_dir.parent.parent, bundle)
        except Exception:  # noqa: BLE001 — 证据包失败不阻断执行链
            pass

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
            "## Agent Contribution",
            "",
            "| Agent | Role | Tasks | Artifacts |",
            "|---|---|---|---|",
        ]
        contrib = {}  # agent → {role, tasks, artifacts}
        for t in state.tasks:
            aid = str(t.get("agent") or "")
            if not aid or aid == "None":
                continue
            entry = contrib.setdefault(
                aid, {"role": role_of.get(aid) or "-", "tasks": 0, "artifacts": []}
            )
            entry["tasks"] += 1
            if t.get("artifact"):
                entry["artifacts"].append(str(t["artifact"]).split("/")[-1])
        for aid in sorted(contrib):
            c = contrib[aid]
            art = ", ".join(c["artifacts"]) or "-"
            lines.append(f"| {aid} | {c['role']} | {c['tasks']} | {art} |")
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
        governance: Optional[Any] = None,
    ) -> dict[str, Any]:
        """单任务执行 + 失败重试 (设计 §7): pending → running → completed/failed。

        失败: retry_count+1; retry_count <= max_retry → 重试一次; 仍失败 →
        status=failed + error (不无限重试, 继续下一任务)。每次状态变更即持久化。
        runner 异常 → 视为失败 (失败安全, 不裸抛)。
        """
        retries = 0
        # S10-073 P0-B: 任务开始自动 Audit (TASK_STARTED, 失败安全)
        try:
            from ..audit.audit_emitter import AuditEmitter
            _emitter = AuditEmitter(workspace=project_dir.parent.parent)
            _emitter.emit(
                "TASK_STARTED", project_id=project_dir.name,
                task_id=str(task.get("id") or ""),
                agent_id=str(task.get("agent") or ""),
                decision_reason=f"任务开始: {task.get('name') or task.get('id')}",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
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
                # S10-083 P0: Patch Delivery — 任务成功 ≠ 完成; 必须
                # patch 应用回项目 + 真实文件 + 校验通过才 completed
                delivery_ok = True
                delivery_msg = ""
                artifact_path = str(outcome.get("artifact") or "")
                if artifact_path and Path(artifact_path).is_file():
                    try:
                        from .delivery import deliver_patch
                        # S10-083: delivery 审计事件独立装配 (不依赖 _emitter 作用域)
                        try:
                            from ..audit.audit_emitter import AuditEmitter
                            _delivery_emitter = AuditEmitter(workspace=project_dir.parent.parent)
                        except Exception:  # noqa: BLE001
                            _delivery_emitter = None
                        patch_text = Path(artifact_path).read_text(encoding="utf-8")
                        delivery = deliver_patch(
                            Path(project_dir), patch_text,
                            emit=_delivery_emitter.emit if _delivery_emitter else None,
                        )
                        task["applied"] = delivery.get("applied", False)
                        task["code_files"] = delivery.get("code_files", 0)
                        task["blocked_files"] = delivery.get("blocked_files", [])
                        delivery_ok = delivery.get("ok", False)
                        delivery_msg = delivery.get("validation") or delivery.get("error") or ""
                    except Exception as exc:  # noqa: BLE001 — 交付异常 → 任务失败
                        delivery_ok = False
                        delivery_msg = f"delivery error: {exc}"
                if not delivery_ok:
                    # 交付失败 (0 代码文件 / apply 失败) → 任务 FAILED, 非 completed
                    task["status"] = "failed"
                    task["error"] = delivery_msg or "交付失败: 项目无真实代码产物"
                    task["retry_count"] = retries
                    self._save_state(project_dir, state)
                    try:
                        from ..audit.audit_emitter import AuditEmitter
                        AuditEmitter(workspace=project_dir.parent.parent).emit(
                            "TASK_FAILED", project_id=project_dir.name,
                            task_id=str(task.get("id") or ""),
                            agent_id=str(task.get("agent") or ""),
                            decision_reason=delivery_msg or "交付失败",
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    return {"success": False, "error": delivery_msg or "交付失败"}
                task["status"] = "completed"
                task["artifact"] = artifact_path
                task["retry_count"] = retries
                task["error"] = None
                self._save_state(project_dir, state)
                # S10-073 P0-B: 任务完成自动 Audit (失败安全)
                try:
                    _emitter.emit(
                        "TASK_COMPLETED", project_id=project_dir.name,
                        task_id=str(task.get("id") or ""),
                        agent_id=str(task.get("agent") or ""),
                        decision_reason=f"任务完成: {task.get('name') or task.get('id')}",
                    )
                except Exception:  # noqa: BLE001
                    pass
                return outcome
            task["error"] = str(outcome.get("error") or "任务执行失败")
            if retries < max_retry:
                retries += 1
                task["retry_count"] = retries
                continue  # 重试 (最多 max_retry 次 — 不无限重试)
            task["status"] = "failed"
            task["retry_count"] = retries
            self._save_state(project_dir, state)
            # S10-073 P0-B: 任务失败自动 Audit (TASK_FAILED, 失败安全)
            try:
                _emitter.emit(
                    "TASK_FAILED", project_id=project_dir.name,
                    task_id=str(task.get("id") or ""),
                    agent_id=str(task.get("agent") or ""),
                    decision_reason=f"任务失败: {task.get('name') or task.get('id')} — {task.get('error', '')[:60]}",
                    result={"error": str(task.get("error") or "")},
                )
            except Exception:  # noqa: BLE001
                pass
            return outcome

    # ------------------------------------------------------------ S10-060 重规划

    def _replan_graph(
        self,
        project_dir: Path,
        plan: Optional[dict[str, Any]],
        dependencies_file: Optional[Path],
    ) -> TaskDependencyGraph:
        """重规划依赖图 (S10-060): 调用方 dependencies_file 优先; 否则从计划任务
        depends_on 构建 (内存图, 不落盘)。失败安全: 图缺失/损坏 → 空图。"""
        graph = TaskDependencyGraph.load(
            dependencies_file if dependencies_file is not None else None
        )
        if graph.to_dict():
            return graph
        for t in (plan or {}).get("tasks") or []:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id") or "")
            if not tid:
                continue
            for d in t.get("depends_on") or []:
                if isinstance(d, dict):
                    continue
                dep = str(d)
                if not dep:
                    continue
                graph.add_task(tid)
                if not graph.add_dependency(tid, dep):
                    continue  # 计划既有环 → 拒绝该边 (失败安全, 不中断)
        return graph

    def _assemble_llm_planning(
        self,
        planning_mode: str,
        llm_reasoning: Optional[Any],
        llm_gap_analyzer: Optional[Any],
        llm_task_proposal: Optional[Any],
        llm_trace: Optional[Any],
        llm_confidence_threshold: float,
    ) -> tuple[Optional[Any], Optional[Any], str]:
        """S10-062 批次 C: LLM planning 组件装配。

        planning_mode: "deterministic" | "llm" | "hybrid" (缺省 hybrid)。
        注入 llm_gap_analyzer/llm_task_proposal → 直接复用; 否则基于
        llm_reasoning 构造 (LLMGapAnalyzer/LLMTaskProposalEngine 默认实现)。
        planning_mode != deterministic 且无任何 LLM 注入 → 回退 deterministic
        (S10-061 完全兼容)。返回 (llm_gap_analyzer, llm_task_proposal, mode)。
        """
        mode = str(planning_mode or "hybrid")
        if mode == "deterministic":
            return None, None, "deterministic"
        if llm_gap_analyzer is None and llm_task_proposal is None and llm_reasoning is None:
            # hybrid/llm 但无 LLM 组件 → deterministic (安全回退)
            return None, None, "deterministic"
        if llm_reasoning is not None:
            if llm_gap_analyzer is None:
                llm_gap_analyzer = LLMGapAnalyzer(
                    provider=llm_reasoning, confidence_threshold=llm_confidence_threshold
                )
            if llm_task_proposal is None:
                llm_task_proposal = LLMTaskProposalEngine(provider=llm_reasoning)
        return llm_gap_analyzer, llm_task_proposal, mode

    def _plan_critic_preflight(
        self,
        project_dir: Path,
        slug: str,
        state: ExecutionState,
        plan: dict[str, Any],
        *,
        replanner: ReplanningEngine,
        plan_critic: PlanCritic,
        task_proposal: Optional[TaskProposalEngine],
        task_validator: Optional[TaskProposalValidator],
        max_replan: int,
        dependencies_file: Optional[Path],
        llm_gap_analyzer: Optional[Any] = None,
        llm_task_proposal: Optional[Any] = None,
        team_run: Optional[Any] = None,
        proposals_file: Optional[Path] = None,
    ) -> str:
        """S10-062 批次 C: PlanCritic 执行前缺口检查 → 提案链 → INSERT。

        只输出 GapAnalysis (不直接改 DAG); 缺口 → TaskProposalEngine.propose
        → Validator → replanner 应用 (INSERT_TASK)。返回 "review" (缺口无法
        自动解决) / "none" (无缺口或已处理)。失败安全: critic 不阻断执行。
        """
        try:
            gaps = plan_critic.review(plan, {}, {})
            if not gaps:
                return "none"
            for gap in gaps:
                detected = gap.get("detected") if isinstance(gap, dict) else getattr(gap, "detected", False)
                action = (
                    gap.get("recommended_action") if isinstance(gap, dict)
                    else getattr(gap, "recommended_action", "")
                )
                if not detected or action not in ("INSERT_TASK", "REPAIR"):
                    continue
                proposals = (
                    llm_task_proposal.propose(gap, {}, existing_tasks=plan.get("tasks") or [])
                    if llm_task_proposal is not None
                    else None
                )
                proposal = (
                    proposals.proposal
                    if proposals is not None and getattr(proposals, "proposal", None)
                    else None
                )
                if proposal is None and task_proposal is not None:
                    proposal = task_proposal.propose(gap, plan.get("tasks") or [], None)
                if proposal is None:
                    return "review"
                valid = (
                    task_validator.validate(
                        proposal, plan.get("tasks") or [], None, state.replan_count, max_replan
                    )
                    if task_validator is not None
                    else {"valid": True}
                )
                if valid.get("valid"):
                    decision = replanner.decide(
                        state.to_dict(), plan, agent_output="plan critic gap",
                        insert_tasks=[proposal.to_dict()],
                    )
                    replanner.record(decision.to_dict())
        except Exception:  # noqa: BLE001 — 失败安全: critic 不阻断执行
            return "none"
        return "none"

    def _replan_on_failure(
        self,
        project_dir: Path,
        state: ExecutionState,
        plan: Optional[dict[str, Any]],
        task: dict[str, Any],
        outcome: dict[str, Any],
        validation: ValidationResult,
        *,
        replanner: ReplanningEngine,
        max_replan: int,
        insert_tasks: Optional[list[dict[str, Any]]],
        dependencies_file: Optional[Path],
        team_run: Optional[TeamRunContext],
        gap_analyzer: Optional[GapAnalyzer] = None,
        task_proposal: Optional[TaskProposalEngine] = None,
        task_validator: Optional[TaskProposalValidator] = None,
        max_auto_insert_tasks: int = 5,
        max_tasks_per_round: int = 3,
        max_total_generated_tasks: int = 10,
        auto_mode: str = "auto_execute",
        proposals_file: Optional[Path] = None,
        # S10-062 批次 C: LLM planning 集成 (LLM=建议, Deterministic=执行)
        planning_mode: str = "deterministic",
        llm_gap_analyzer: Optional[Any] = None,
        llm_task_proposal: Optional[Any] = None,
        llm_reasoning: Optional[Any] = None,
        llm_trace: Optional[Any] = None,
        llm_confidence_threshold: float = 0.5,
        # S10-063: 生产治理 (budget/review/policy/loop guard — 失败安全可选)
        governance: Optional[Any] = None,
    ) -> str:
        """任务失败后: 观察 → Gap 分析 (S10-061) → ReplanningEngine.decide →
        记录 → 应用 (改 DAG/Plan)。

        返回信号: "none" (KEEP_PLAN — Repair 路径不变) / "continue" (计划已改,
        队列继续) / "review" (REQUEST_REVIEW — 停止队列, 需人工评审)。

        S10-061 批次 B (Autonomous Gap Resolution 集成, 设计 §2/§6/§7):
        - gap_analyzer 提供 → GapAnalyzer.analyze (失败上下文) → 落盘
          gap_analysis.json (资产 G9) → 同一 source_gap 防重 (GAP G6: 第一次
          INSERT, 再失败 RETRY/REPAIR, 第三次 REQUEST_REVIEW — 不无限 INSERT);
        - decide(gap_analysis=...) → TaskProposalEngine.propose + Validator
          (引擎生成, 非调用方注入) → INSERT_TASK → _insert_tasks + plan_version+1
          → 继续执行; 提案落盘 task_proposals.json (资产 G9);
        - 防无限 (GAP G5): max_auto_insert_tasks / max_tasks_per_round /
          max_total_generated_tasks (decide 内生效);
        - auto_mode 安全边界 (GAP G7): auto_execute / auto_propose_review /
          request_review (decide 内生效)。

        Repair vs Replanning 分离 (设计 §7 P6):
        - Repair:     任务失败 → repair_task.json (任务级, quality.RepairManager)
        - Replanning: 计划不适合现实 → 改 DAG/Plan (计划级, 本方法)
        - 两者独立: repair 已在上游创建, 本方法只处理计划级偏差。
        """
        outcome = outcome if isinstance(outcome, dict) else {}
        plan = plan if isinstance(plan, dict) else {"tasks": []}
        graph = self._replan_graph(project_dir, plan, dependencies_file)
        agent_output = str(
            outcome.get("agent_output")
            or outcome.get("output")
            or outcome.get("error")
            or ""
        )
        failures = [
            {
                "task_id": str(task.get("id") or ""),
                "name": str(task.get("name") or task.get("id") or ""),
                "error": str(
                    outcome.get("error")
                    or task.get("error")
                    or "; ".join(validation.errors)
                    or "任务执行失败"
                ),
            }
        ]
        ctx = WorkspaceContext.load(project_dir)
        plan_tasks = [t for t in (plan.get("tasks") or []) if isinstance(t, dict)]

        # ---- S10-061 批次 B: Gap 分析 (失败上下文 → GapAnalysis → gap_analysis.json)
        analysis = None
        # ---- S10-062 批次 C: LLM Gap 分析优先 (llm/hybrid) — LLM=建议,
        # ---- Deterministic=执行; LLM 失败 → deterministic fallback
        if (
            llm_gap_analyzer is not None
            and planning_mode in ("llm", "hybrid")
        ):
            try:
                ctx_builder = ContextBuilder()
                llm_ctx = ctx_builder.build(project_dir, str(Path(project_dir).name))
                llm_result = llm_gap_analyzer.analyze(llm_ctx, {"task": task, "result": outcome})
                llm_analysis = (
                    getattr(llm_result, "analysis", None)
                    if llm_result is not None
                    else None
                )
                if llm_analysis is not None and getattr(llm_analysis, "detected", False):
                    analysis = llm_analysis
                    if llm_trace is not None:
                        try:
                            trace_rec = llm_trace.record(
                                operation="analyze_gap",
                                provider=getattr(llm_result, "provider", "llm") or "llm",
                                model=getattr(llm_result, "model", "") or "",
                                input_hash="",
                                output="",
                                parsed_result=analysis.to_dict() if hasattr(analysis, "to_dict") else {},
                                confidence=getattr(llm_analysis, "confidence", 0.0) or 0.0,
                                token_usage={},
                                latency=0.0,
                                fallback_used=bool(getattr(llm_result, "fallback_used", False)),
                                validation_result={"valid": True},
                                final_decision="llm_gap",
                            )
                            # S10-065: planning trace 记录 → cost ledger 同步
                            # (trace_id + final_decision 关联 — 成本可追溯)
                            self._sync_planning_cost(
                                governance, trace_rec, "GAP_ANALYSIS", task
                            )
                        except Exception:  # noqa: BLE001
                            pass
            except Exception:  # noqa: BLE001 — LLM 失败 → deterministic fallback
                analysis = None
        if analysis is None and gap_analyzer is not None:
            try:
                # 执行失败 (outcome.success=False) → 不传验证失败信号 (缺口信号优先,
                # 避免 validation_failure 遮蔽 agent_output 缺口 — 验证门失败另有
                # validation_failure→REPAIR 路径); 执行成功但验证失败 → 验证缺口
                validation_signal = (
                    {"success": False, "errors": list(validation.errors)}
                    if bool(outcome.get("success")) and not validation.success
                    else None
                )
                analysis = gap_analyzer.analyze(
                    workspace=ctx,
                    task=task,
                    result=outcome,
                    validation=validation_signal,
                    agent_output=agent_output,
                    failures=failures,
                    existing_tasks=plan_tasks,
                    dag=graph,
                    prev_decisions=replanner.previous_decisions(),
                )
                if analysis is not None:
                    gap_analyzer.record(analysis)
            except Exception:  # noqa: BLE001 — 失败安全: 分析异常 → S10-060 路径
                analysis = None

        # ---- S10-061 批次 B: 同一 source_gap 防重 (GAP G6) — 第一次 INSERT,
        # ---- 再失败 RETRY/REPAIR (Repair 路径, 不再插入), 第三次 REQUEST_REVIEW
        source_gap = self._gap_key(analysis)
        if source_gap and self._gap_insert_action(analysis):
            occurrences = 1 + sum(
                1
                for d in replanner.previous_decisions()
                if str(d.get("source_gap") or "") == source_gap
            )
            if occurrences >= 3:
                decision_dict = ReplanningEngine._normalize(
                    {
                        "decision": ReplanningEngine.DECISION_REQUEST_REVIEW,
                        "reason": (
                            f"同一 source_gap {source_gap!r} 已出现 {occurrences} 次 — "
                            f"已 INSERT 过且再次失败, 停止自主重规划, 需人工评审 "
                            f"(REQUEST_REVIEW)"
                        ),
                        "affected_tasks": [f["task_id"] for f in failures if f.get("task_id")],
                        "plan_version": state.plan_version,
                        "source_gap": source_gap,
                    }
                )
                signal = self._apply_replan(
                    project_dir,
                    state,
                    plan,
                    decision_dict,
                    dependencies_file=dependencies_file,
                    team_run=team_run,
                )
                replanner.record(decision_dict)
                return signal
            if occurrences >= 2:
                decision_dict = ReplanningEngine._normalize(
                    {
                        "decision": ReplanningEngine.DECISION_KEEP_PLAN,
                        "reason": (
                            f"同一 source_gap {source_gap!r} 已 INSERT 过且再次失败 — "
                            f"不再插入, 走任务级 Repair 路径 (RETRY/REPAIR)"
                        ),
                        "affected_tasks": [f["task_id"] for f in failures if f.get("task_id")],
                        "plan_version": state.plan_version,
                        "source_gap": source_gap,
                    }
                )
                replanner.record(decision_dict)
                return "none"

        # ---- 决策: gap_analysis 结果驱动自动提案 (S10-061) / S10-060 路径
        generated_count = sum(
            len(d.get("new_tasks") or [])
            for d in replanner.previous_decisions()
            if d.get("decision") == "INSERT_TASK" and d.get("source_gap")
        )
        # ---- S10-062 批次 C: LLM 任务提案优先 (llm/hybrid + LLM gap 检出 INSERT)
        llm_proposal = None
        if (
            llm_task_proposal is not None
            and planning_mode in ("llm", "hybrid")
            and analysis is not None
        ):
            try:
                action = (
                    getattr(analysis, "recommended_action", "")
                    if not isinstance(analysis, dict)
                    else analysis.get("recommended_action", "")
                )
                if action in ("INSERT_TASK", "REPAIR"):
                    llm_res = llm_task_proposal.propose(
                        analysis,
                        {},
                        existing_tasks=plan_tasks,
                        dag=graph,
                    )
                    if llm_res is not None and getattr(llm_res, "proposal", None) is not None:
                        llm_proposal = llm_res.proposal
                        if llm_trace is not None:
                            try:
                                trace_rec = llm_trace.record(
                                    operation="propose_task",
                                    provider=getattr(llm_res, "provider", "llm") or "llm",
                                    model=getattr(llm_res, "model", "") or "",
                                    input_hash="",
                                    output="",
                                    parsed_result=llm_proposal.to_dict() if hasattr(llm_proposal, "to_dict") else {},
                                    confidence=getattr(llm_res, "confidence", 0.0) or 0.0,
                                    token_usage={},
                                    latency=0.0,
                                    fallback_used=bool(getattr(llm_res, "fallback_used", False)),
                                    validation_result={"valid": True},
                                    final_decision="llm_proposal",
                                )
                                # S10-065: planning trace 记录 → cost ledger 同步
                                self._sync_planning_cost(
                                    governance, trace_rec, "PLANNING", task
                                )
                            except Exception:  # noqa: BLE001
                                pass
            except Exception:  # noqa: BLE001 — LLM 失败 → deterministic 路径
                llm_proposal = None
        decision = replanner.decide(
            state.to_dict(),
            plan,
            failures=failures,
            validation={
                "success": bool(validation.success),
                "errors": list(validation.errors),
            },
            agent_output=agent_output,
            dependency_graph=graph,
            workspace=ctx,
            max_replan=max_replan,
            plan_version=state.plan_version,
            replan_count=state.replan_count,
            insert_tasks=insert_tasks,
            gap_analysis=analysis,
            task_proposal=task_proposal,
            task_validator=task_validator,
            llm_proposal=llm_proposal,
            auto_mode=auto_mode,
            max_auto_insert_tasks=max_auto_insert_tasks,
            max_tasks_per_round=max_tasks_per_round,
            max_total_generated_tasks=max_total_generated_tasks,
            generated_count=generated_count,
        )
        # 先应用 (可能补充 dependency_changes — 环拒绝边), 后记录 (资产完整落盘)
        decision_dict = ReplanningEngine._normalize(decision)
        signal = self._apply_replan(
            project_dir,
            state,
            plan,
            decision_dict,
            dependencies_file=dependencies_file,
            team_run=team_run,
        )
        replanner.record(decision_dict)
        # ---- S10-061 批次 B: 自动提案资产化 — task_proposals.json (GAP G9)
        if decision_dict.get("new_tasks"):
            self._record_proposals(project_dir, decision_dict["new_tasks"], proposals_file)
        return signal

    # ------------------------------------------------------------ S10-061 资产/防重

    @staticmethod
    def _sync_planning_cost(
        governance: Optional[Any],
        trace_rec: Any,
        purpose: str,
        task: Optional[dict[str, Any]],
    ) -> None:
        """S10-065: planning trace 记录 → cost ledger 同步 (trace_id 关联)。

        planning_trace 落盘后同步一条成本记录 (同 trace_id + final_decision
        → planning_decision_id) — 回答"这次为什么花了这些钱"。失败安全:
        无 governance/ledger/记录异常 → 不抛, 不中断执行流。
        """
        if governance is None or trace_rec is None or governance.cost_ledger is None:
            return
        try:
            governance.cost_ledger.record(
                {
                    "project_id": governance.project_id,
                    "task_id": str((task or {}).get("id") or ""),
                    "agent_id": str((task or {}).get("agent") or ""),
                    "purpose": str(purpose or "PLANNING"),
                    "provider": str(trace_rec.get("provider") or ""),
                    "model": str(trace_rec.get("model") or ""),
                    "latency": float(trace_rec.get("latency") or 0.0),
                },
                trace_id=str(trace_rec.get("trace_id") or "") or None,
                planning_decision_id=str(trace_rec.get("final_decision") or "") or None,
            )
        except Exception:  # noqa: BLE001 — 失败安全: 同步失败不中断执行流
            pass

    @staticmethod
    def _gap_key(analysis: Any) -> str:
        """GapAnalysis/dict → source_gap 标识 "{gap_type}@{source_task_id}"。

        未检出/无 gap_type → "" (不参与同一 gap 防重 — P2)。
        """
        if analysis is None:
            return ""
        d = (
            analysis.to_dict()
            if hasattr(analysis, "to_dict")
            else (analysis if isinstance(analysis, dict) else {})
        )
        if not isinstance(d, dict) or not d.get("detected"):
            return ""
        gtype = str(d.get("gap_type") or "")
        if not gtype:
            return ""
        sid = str(d.get("source_task_id") or "")
        return f"{gtype}@{sid}" if sid else gtype

    @staticmethod
    def _gap_insert_action(analysis: Any) -> bool:
        """缺口建议动作是否为 INSERT_TASK (同一 gap 防重仅作用于插入路径)。"""
        if analysis is None:
            return False
        d = (
            analysis.to_dict()
            if hasattr(analysis, "to_dict")
            else (analysis if isinstance(analysis, dict) else {})
        )
        return (
            isinstance(d, dict)
            and str(d.get("recommended_action") or "") == "INSERT_TASK"
        )

    def _record_proposals(
        self,
        project_dir: Path,
        proposals: list[Any],
        file: Optional[Path] = None,
    ) -> None:
        """task_proposals.json 落盘 (S10-061 资产 G9): append 有效提案, 失败安全。

        记录面: 自动生成提案 (带 source_gap 的决策 new_tasks); 按 task_id 去重
        (重复提案不追加); 读写异常 → 不抛 (资产记录不中断执行流)。
        """
        path = Path(file) if file is not None else project_dir / "task_proposals.json"
        try:
            records: list[dict[str, Any]] = []
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    records = [dict(r) for r in data if isinstance(r, dict)]
            known = {
                str(r.get("task_id") or r.get("id") or "") for r in records
            }
            for p in proposals:
                if not isinstance(p, dict):
                    continue
                tid = str(p.get("task_id") or p.get("id") or "")
                if not tid or tid in known:
                    continue
                records.append(dict(p))
                known.add(tid)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断
            pass

    def _apply_replan(
        self,
        project_dir: Path,
        state: ExecutionState,
        plan: dict[str, Any],
        decision: Any,
        *,
        dependencies_file: Optional[Path],
        team_run: Optional[TeamRunContext],
    ) -> str:
        """应用 ReplanDecision → 同步 state/plan/DAG → 返回信号 (none/continue/review)。

        入参为归一化 dict (ReplanDecision → to_dict) — 应用期间可能补充
        dependency_changes (环拒绝边), 由调用方负责记录 (先应用后记录)。
        """
        if isinstance(decision, ReplanDecision):
            decision = decision.to_dict()
        elif not isinstance(decision, dict):
            decision = {}
        name = str(decision.get("decision") or ReplanningEngine.DECISION_KEEP_PLAN)
        affected = [
            str(t) for t in (decision.get("affected_tasks") or []) if not isinstance(t, dict)
        ]
        if name == ReplanningEngine.DECISION_KEEP_PLAN:
            return "none"
        if name == ReplanningEngine.DECISION_REQUEST_REVIEW:
            state.replan_count += 1
            state.last_replan_reason = str(decision.get("reason") or "")
            self._save_state(project_dir, state)
            return "review"
        if name == ReplanningEngine.DECISION_INSERT_TASK:
            self._insert_tasks(
                project_dir,
                state,
                plan,
                decision.get("new_tasks") or [],
                dependencies_file=dependencies_file,
                decision=decision,
            )
            self._bump_plan(
                project_dir, state, plan, decision, dependencies_file=dependencies_file,
                team_run=team_run,
            )
            return "continue"
        if name == ReplanningEngine.DECISION_SPLIT_TASK:
            # 原任务标记 split (计划级产物, 不再执行); 拆分任务插入 (同 INSERT)
            for tid in affected:
                self._mark_plan_task(state, tid, "split", str(decision.get("reason") or ""))
            self._insert_tasks(
                project_dir,
                state,
                plan,
                decision.get("new_tasks") or [],
                dependencies_file=dependencies_file,
                decision=decision,
            )
            self._bump_plan(
                project_dir, state, plan, decision, dependencies_file=dependencies_file,
                team_run=team_run,
            )
            return "continue"
        if name == ReplanningEngine.DECISION_MODIFY_TASK:
            for m in decision.get("modified_tasks") or []:
                if not isinstance(m, dict):
                    continue
                tid = str(m.get("id") or "")
                if not tid:
                    continue
                for t in state.tasks:
                    if str(t.get("id")) == tid:
                        if m.get("name"):
                            t["name"] = str(m["name"])
                        if m.get("requirement") and not m.get("name"):
                            t["name"] = str(m["requirement"])
                for pt in plan.get("tasks") or []:
                    if isinstance(pt, dict) and str(pt.get("id")) == tid:
                        if m.get("name"):
                            pt["name"] = str(m["name"])
            self._bump_plan(
                project_dir, state, plan, decision, dependencies_file=dependencies_file,
                team_run=team_run,
            )
            return "continue"
        if name == ReplanningEngine.DECISION_SKIP_TASK:
            for tid in affected:
                self._mark_plan_task(state, tid, "skipped", str(decision.get("reason") or ""))
            self._bump_plan(
                project_dir, state, plan, decision, dependencies_file=dependencies_file,
                team_run=team_run,
            )
            return "continue"
        if name == ReplanningEngine.DECISION_BLOCK_TASK:
            for tid in affected:
                self._mark_plan_task(state, tid, "blocked", str(decision.get("reason") or ""))
            self._bump_plan(
                project_dir, state, plan, decision, dependencies_file=dependencies_file,
                team_run=team_run,
            )
            return "continue"
        if name == ReplanningEngine.DECISION_REORDER_TASKS:
            order = [
                str(t) for t in (decision.get("execution_order") or []) if not isinstance(t, dict)
            ]
            if order:
                pos = {tid: i for i, tid in enumerate(order)}
                pending = [t for t in state.tasks if str(t.get("status")) == "pending"]
                done = [t for t in state.tasks if str(t.get("status")) != "pending"]
                pending.sort(key=lambda t: pos.get(str(t.get("id")), len(order)))
                state.tasks = done + pending
                plan_tasks = [
                    t for t in (plan.get("tasks") or []) if isinstance(t, dict)
                ]
                plan["tasks"] = sorted(
                    plan_tasks,
                    key=lambda t: pos.get(str(t.get("id")), len(order)),
                )
                plan["count"] = len(plan["tasks"])
            self._bump_plan(
                project_dir, state, plan, decision, dependencies_file=dependencies_file,
                team_run=team_run,
            )
            return "continue"
        return "none"

    @staticmethod
    def _mark_plan_task(
        state: ExecutionState, task_id: str, status: str, reason: str
    ) -> None:
        """计划级任务标记 (skipped/blocked/split — 不再执行, 可解释)。"""
        for t in state.tasks:
            if str(t.get("id")) == task_id and str(t.get("status")) != "completed":
                t["status"] = status
                t["error"] = reason
                if status == "skipped":
                    t.setdefault("validation", "passed")

    def _insert_tasks(
        self,
        project_dir: Path,
        state: ExecutionState,
        plan: dict[str, Any],
        new_tasks: list[Any],
        *,
        dependencies_file: Optional[Path],
        decision: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        """插入新任务 (INSERT_TASK/SPLIT_TASK): state + plan + DAG + 落盘同步。

        新任务候选由调用方提供 (设计: 不自动生成任务内容); id 缺失 → 自动推导
        (task-<n>, 仅标识不生成内容); 已存在同 id → 跳过 (幂等)。
        DAG 更新: 新任务注册 + 依赖边 (环 → 拒绝该边, 记录 decision 的
        dependency_changes, 不中断)。execution_plan.json / tasks.json (存在时) 同步。
        """
        inserted: list[str] = []
        existing = {str(t.get("id")) for t in state.tasks if t.get("id")}
        graph = self._replan_graph(project_dir, plan, dependencies_file)
        plan_tasks = [t for t in (plan.get("tasks") or []) if isinstance(t, dict)]
        plan_ids = {str(t.get("id")) for t in plan_tasks if t.get("id")}
        for cand in new_tasks:
            if not isinstance(cand, dict):
                continue
            tid = str(cand.get("id") or "")
            if not tid:
                tid = f"task-{len(state.tasks) + 1}"
            if tid in existing:
                continue
            record = self._task_record({**cand, "id": tid})
            state.tasks.append(record)
            existing.add(tid)
            # DAG: 注册节点 + 依赖边 (环 → 拒绝该边, 记录 dependency_changes, 不中断)
            graph.add_task(tid)
            for d in cand.get("depends_on") or []:
                if isinstance(d, dict):
                    continue
                dep = str(d)
                if not dep:
                    continue
                if not graph.add_dependency(tid, dep):
                    if decision is not None:
                        decision.setdefault("dependency_changes", []).append(
                            {
                                "action": "reject_add_dependency",
                                "task": tid,
                                "depends_on": dep,
                                "reason": "cyclic dependency",
                            }
                        )
            # plan 同步 (候选原样 + 推导 id)
            if tid not in plan_ids:
                plan_tasks.append({**cand, "id": tid})
                plan_ids.add(tid)
            inserted.append(tid)
        plan["tasks"] = plan_tasks
        plan["count"] = len(plan_tasks)
        # DAG 落盘 (仅调用方提供文件时 — solo 模式不引入新资产文件)
        if dependencies_file is not None:
            try:
                graph.save(dependencies_file)
            except Exception:  # noqa: BLE001 — 失败安全: DAG 落盘失败不中断
                pass
        # tasks.json 同步 (存在才更新 — 失败安全; 无 tasks.json → 仅 plan/state)
        tasks_file = project_dir / "tasks.json"
        if tasks_file.is_file():
            try:
                data = _read_json(tasks_file)
                known = {
                    str(t.get("id"))
                    for t in (data.get("tasks") or [])
                    if isinstance(t, dict)
                }
                added = [
                    {**t, "id": str(t.get("id") or "")}
                    for t in new_tasks
                    if isinstance(t, dict) and str(t.get("id") or "") and str(t.get("id")) not in known
                ]
                if added:
                    data.setdefault("tasks", []).extend(added)
                    data["count"] = len(data["tasks"])
                    _write_json(tasks_file, data)
            except Exception:  # noqa: BLE001 — 失败安全: tasks.json 同步失败不中断
                pass
        self._save_state(project_dir, state)
        return inserted

    def _bump_plan(
        self,
        project_dir: Path,
        state: ExecutionState,
        plan: dict[str, Any],
        decision: dict[str, Any],
        *,
        dependencies_file: Optional[Path],
        team_run: Optional[TeamRunContext],
    ) -> None:
        """计划版本推进 (S10-060 P3): plan_version v→v+1 + replan_count+1 +
        last_replan_reason + execution_plan.json/execution_state.json/tasks 同步。

        落盘后可回答"AI Factory 为什么改变了原来的开发计划" (replanning_decisions
        + last_replan_reason 双资产)。team mode → team_execution_state 同步。
        """
        state.plan_version += 1
        state.replan_count += 1
        state.last_replan_reason = str(decision.get("reason") or "")
        plan["plan_version"] = state.plan_version
        plan["replan_count"] = state.replan_count
        plan["last_replan_reason"] = state.last_replan_reason
        self._save_state(project_dir, state)
        _write_json(project_dir / "execution_plan.json", plan)
        if team_run is not None:
            TeamExecutionState.sync_plan_version(project_dir, state.plan_version)
