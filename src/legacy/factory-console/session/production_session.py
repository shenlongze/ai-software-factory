"""factory-console/session/production_session.py — ProductionSession (S10-065 P0-2)。

统一生产过程视图: 聚合 ExecutionState (execution_state.json) + TeamExecutionState
(team_execution_state.json) + CostLedger (cost_records.json) + ReviewGate
(review_records.json) + ProjectBudget (project_budget.json) + product.json →
统一用户视图 (phase/progress/team/budget/cost/governance/pending_review)。

组件:
- ProductionPhase — 生产阶段常量 (STARTING/PLANNING/EXECUTING/VALIDATING/
  REPLANNING/WAITING_FOR_REVIEW/USER_ACCEPTANCE/DELIVERED/BLOCKED/FAILED)
- ProductionEvent — 生产事件 {timestamp, phase, message, task_id, agent_id,
  plan_version}
- ProductionSession — from_project (聚合) / get_status / get_progress /
  get_team_status / get_cost_status / get_governance_status / get_review /
  refresh / view / to_markdown
- PHASE_LABELS — 阶段 → 中文标签 (to_markdown 用户可读)

不重新实现 Orchestrator — 只读取/聚合现有状态 (GAP G2 复用口径)。

设计: docs/sprint10/S10-065-interactive-discovery-design.md §3
GAP: docs/sprint10/S10-065-gap-analysis.md G2
边界: 只读聚合 (不改写任何现有资产); 缺失/损坏文件 → 空聚合失败安全 (永不抛);
纯标准库 (json/dataclasses/datetime/pathlib), 零新依赖。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .budget import ProjectBudget
from .cost_ledger import CostLedger
from .orchestrator import ExecutionState
from .product import ProductIntent
from .review_gate import ReviewGate
from .team_state import TeamExecutionState

# ---------------------------------------------------------------- 阶段常量

#: execution_state.json 文件名 (orchestrator 资产口径)
EXECUTION_STATE_FILE_NAME = "execution_state.json"

#: 资产文件名 (projects/<slug>/ 下)
PRODUCT_FILE_NAME = "product.json"
PROJECT_BUDGET_FILE_NAME = "project_budget.json"


class ProductionPhase:
    """生产阶段常量 (设计 §3 — 值小写)。"""

    STARTING = "starting"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    REPLANNING = "replanning"
    WAITING_FOR_REVIEW = "waiting_for_review"
    USER_ACCEPTANCE = "user_acceptance"
    DELIVERED = "delivered"
    BLOCKED = "blocked"
    FAILED = "failed"

    #: 全部合法阶段
    PHASES: tuple[str, ...] = (
        STARTING,
        PLANNING,
        EXECUTING,
        VALIDATING,
        REPLANNING,
        WAITING_FOR_REVIEW,
        USER_ACCEPTANCE,
        DELIVERED,
        BLOCKED,
        FAILED,
    )


#: 阶段 → 中文标签 (to_markdown 用户可读)
PHASE_LABELS: dict[str, str] = {
    ProductionPhase.STARTING: "准备中",
    ProductionPhase.PLANNING: "规划中",
    ProductionPhase.EXECUTING: "正在开发中",
    ProductionPhase.VALIDATING: "验证中",
    ProductionPhase.REPLANNING: "计划调整中",
    ProductionPhase.WAITING_FOR_REVIEW: "等待人工评审",
    ProductionPhase.USER_ACCEPTANCE: "待验收",
    ProductionPhase.DELIVERED: "已交付",
    ProductionPhase.BLOCKED: "已阻塞",
    ProductionPhase.FAILED: "失败",
}

#: 团队角色展示顺序 (to_markdown 团队行 — PM → Architect → Backend → Frontend → QA)
TEAM_ROLE_ORDER: tuple[str, ...] = ("PM", "Architect", "Backend", "Frontend", "QA")

#: 阶段状态符号 (to_markdown: ✓ 完成 / ● 进行中 / ○ 空闲)
_TEAM_MARK_DONE = "✓"
_TEAM_MARK_ACTIVE = "●"
_TEAM_MARK_IDLE = "○"


@dataclass
class ProductionEvent:
    """生产事件 (设计 §3): timestamp/phase/message/task_id/agent_id/plan_version。"""

    timestamp: str = ""
    phase: str = ""
    message: str = ""
    task_id: str = ""
    agent_id: str = ""
    plan_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """→ dict (事件视图)。"""
        return {
            "timestamp": self.timestamp,
            "phase": self.phase,
            "message": self.message,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "plan_version": int(self.plan_version),
        }


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (事件时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    """读取 JSON (缺失/损坏 → None, 失败安全)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 失败安全
        return None


def _agent_role(agent_id: str) -> str:
    """Agent id → 角色标签 (PM/Architect/Backend/Frontend/QA; 未知 → 首段大写)。"""
    key = str(agent_id or "").strip().lower().replace("_", "-")
    if key in ("pm", "pm-agent", "pm-1", "product-manager", "product-manager-agent"):
        return "PM"
    if key in ("architect", "architect-agent", "architect-1", "architecture"):
        return "Architect"
    if key in ("backend", "backend-1", "backend-agent", "backend-dev"):
        return "Backend"
    if key in (
        "frontend",
        "frontend-1",
        "frontend-agent",
        "flutter-dev",
        "frontend-dev",
    ):
        return "Frontend"
    if key in ("qa", "qa-agent", "qa-1", "test", "test-agent", "tester"):
        return "QA"
    if not key:
        return "?"
    head = key.split("-")[0]
    return head[:1].upper() + head[1:]


def _map_phase(
    state: Optional[ExecutionState],
    pending_review: bool,
    governance_status: str,
) -> str:
    """ExecutionState 状态/生命周期 + 治理/评审 → ProductionPhase (优先级映射)。

    优先级 (确定性, 测试可精确断言):
    1. status failed → FAILED
    2. status/governance blocked → BLOCKED (含 paused — 暂停=停止)
    3. status review_required / governance waiting_for_review / pending_review
       → WAITING_FOR_REVIEW
    4. status replanning → REPLANNING
    5. lifecycle DELIVERED / USER_ACCEPTANCE / TESTING|VALIDATION_PASS /
       DEVELOPMENT|EXECUTION_READY / ENGINEERING_READY|PRODUCT_DEFINED / IDEA
    6. 未知/缺失 → STARTING (失败安全)
    """
    if state is None:
        return ProductionPhase.STARTING
    status = str(state.status or "")
    lifecycle = str(state.lifecycle or "") or status
    gov = str(governance_status or "")

    if status == "failed":
        return ProductionPhase.FAILED
    if status == "blocked" or gov == "blocked" or status == "paused":
        return ProductionPhase.BLOCKED
    if (
        status in ("waiting_for_review", "review_required")
        or gov == "waiting_for_review"
        or pending_review
    ):
        return ProductionPhase.WAITING_FOR_REVIEW
    if status == "replanning":
        return ProductionPhase.REPLANNING

    from .pipeline import Lifecycle

    if lifecycle == Lifecycle.DELIVERED:
        return ProductionPhase.DELIVERED
    if lifecycle == Lifecycle.USER_ACCEPTANCE:
        return ProductionPhase.USER_ACCEPTANCE
    if lifecycle in (Lifecycle.VALIDATION_PASS, Lifecycle.TESTING):
        return ProductionPhase.VALIDATING
    if lifecycle in (Lifecycle.DEVELOPMENT, Lifecycle.EXECUTION_READY):
        return ProductionPhase.EXECUTING
    if lifecycle in (Lifecycle.ENGINEERING_READY, Lifecycle.PRODUCT_DEFINED):
        return ProductionPhase.PLANNING
    if lifecycle == Lifecycle.IDEA:
        return ProductionPhase.STARTING
    return ProductionPhase.STARTING


def _current_task_info(tasks: list[dict[str, Any]]) -> tuple[str, str]:
    """当前任务/Agent: 优先 running 任务; 否则第一个 pending (下一个执行)。"""
    if not tasks:
        return "", ""
    for task in tasks:
        if str(task.get("status")) == "running":
            return (
                str(task.get("name") or task.get("id") or ""),
                str(task.get("agent") or ""),
            )
    for task in tasks:
        if str(task.get("status")) == "pending":
            return (
                str(task.get("name") or task.get("id") or ""),
                str(task.get("agent") or ""),
            )
    return "", ""


def _task_counts(tasks: list[dict[str, Any]]) -> tuple[int, int]:
    """任务计数 (completed, total)。"""
    total = len(tasks)
    completed = sum(
        1 for t in tasks if str(t.get("status")) == "completed"
    )
    return completed, total


def _agent_display(agent_id: str) -> str:
    """Agent id → 展示名 (to_markdown: 首字母大写短名)。"""
    role = _agent_role(agent_id)
    if role != "?":
        return role
    return str(agent_id or "?")


# ---------------------------------------------------------------- 会话模型

@dataclass
class ProductionSession:
    """统一生产过程视图 (设计 §3): 聚合现有状态, 不重新实现 Orchestrator。

    字段 (from_project 聚合填充):
    - project_id — 项目 slug
    - product_id — 产品名 (product.json name; 缺失 → slug)
    - lifecycle_state — Lifecycle 原始状态 (execution_state.lifecycle)
    - current_phase — ProductionPhase (状态映射)
    - current_task / current_agent — 进行中/下一个任务
    - team_members — 团队状态列表 [{agent, role, status, total, completed}]
    - completed_tasks / total_tasks — 任务计数
    - plan_version / replan_count — 计划版本/重规划次数
    - budget_limit / current_cost / cost_percentage — 预算/成本
    - governance_status / governance_reason — 治理状态/原因
    - pending_review — 是否有待人工评审
    - last_event / events — 事件记录 (只读聚合, 内存)
    - updated_at — 最近聚合时间
    """

    project_id: str = ""
    product_id: str = ""
    lifecycle_state: str = ""
    current_phase: str = ProductionPhase.STARTING
    current_task: str = ""
    current_agent: str = ""
    team_members: list[dict[str, Any]] = field(default_factory=list)
    completed_tasks: int = 0
    total_tasks: int = 0
    plan_version: int = 1
    replan_count: int = 0
    budget_limit: float = 0.0
    current_cost: float = 0.0
    cost_percentage: float = 0.0
    governance_status: str = ""
    governance_reason: str = ""
    pending_review: bool = False
    last_event: Optional[ProductionEvent] = None
    events: list[ProductionEvent] = field(default_factory=list)
    updated_at: str = ""

    #: 内部: 聚合输入源 (refresh 复用 — 注入的 ledger/gate/budget 保持)
    _project_dir: Path = field(default_factory=Path, repr=False)
    _budget: Any = field(default=None, repr=False)
    _cost_ledger: Any = field(default=None, repr=False)
    _review_gate: Any = field(default=None, repr=False)
    _execution_state: Any = field(default=None, repr=False)
    _team_state: Any = field(default=None, repr=False)

    # ------------------------------------------------------------ 聚合入口

    @classmethod
    def from_project(
        cls,
        project_dir: Any,
        slug: str,
        *,
        budget: Any = None,
        cost_ledger: Any = None,
        review_gate: Any = None,
    ) -> "ProductionSession":
        """聚合项目现有状态 → ProductionSession (只读, 失败安全)。

        数据源 (projects/<slug>/):
        - execution_state.json → ExecutionState (status/lifecycle/tasks/plan_version)
        - team_execution_state.json → TeamExecutionState (团队状态)
        - cost_records.json → CostLedger.aggregate (成本)
        - review_records.json → ReviewGate.status/pending (评审)
        - project_budget.json → ProjectBudget (预算上限; budget 参数优先)
        - product.json → ProductIntent (产品名)

        budget: float (USD 上限) | ProjectBudget | dict {max_total_cost} |
        None (→ project_budget.json, 缺失 → 0.0 无上限)。
        """
        project_dir = Path(project_dir)
        session = cls(project_id=str(slug or ""), updated_at=_now_iso())
        session._project_dir = project_dir
        session._budget = budget
        session._cost_ledger = cost_ledger
        session._review_gate = review_gate
        session._load_state(project_dir, slug)
        session._record_event("生产会话创建", phase=session.current_phase)
        return session

    # ------------------------------------------------------------ 聚合实现

    def _load_state(self, project_dir: Path, slug: str) -> None:
        """读入全部资产并聚合 (from_project/refresh 共用)。"""
        # ① ExecutionState (缺失/损坏 → None, 失败安全)
        state: Optional[ExecutionState] = None
        try:
            state = ExecutionState.load(project_dir / EXECUTION_STATE_FILE_NAME)
        except Exception:  # noqa: BLE001 — 损坏 → 空聚合
            state = None
        self._execution_state = state

        # ② TeamExecutionState (缺失 → 缺省骨架)
        team_state = TeamExecutionState.get(project_dir)
        self._team_state = team_state

        # ③ ReviewGate → pending_review / governance 来源
        gate = self._review_gate
        if gate is None:
            gate = ReviewGate.for_project(project_dir)
        gate_status = "none"
        try:
            gate_status = str(gate.status(project_id=slug) or "none")
        except Exception:  # noqa: BLE001 — 失败安全
            gate_status = "none"
        pending_review = gate_status == "waiting"

        # ④ 治理状态 (execution_state.governance_status 优先; 评审 waiting 兜底)
        governance_status = ""
        governance_reason = ""
        if state is not None:
            governance_status = str(state.governance_status or "")
            governance_reason = str(state.governance_reason or "")
        if not governance_status and pending_review:
            governance_status = "waiting_for_review"
            governance_reason = "存在待人工评审 (ReviewGate)"
        if not governance_status and gate_status == "rejected":
            governance_status = "rejected"
            governance_reason = "最近一次评审被拒绝"

        # ⑤ 阶段映射 + 任务信息
        phase = _map_phase(state, pending_review, governance_status)
        tasks = list(state.tasks) if state is not None else []
        current_task, current_agent = _current_task_info(tasks)
        completed, total = _task_counts(tasks)

        # ⑥ 计划版本/重规划 (execution_state 优先; team_state 兜底)
        plan_version = int(state.plan_version or 1) if state is not None else 1
        replan_count = int(state.replan_count or 0) if state is not None else 0
        if state is None:
            plan_version = int(team_state.get("plan_version") or 1)

        # ⑦ 成本/预算
        ledger = self._cost_ledger
        if ledger is None:
            ledger = CostLedger.for_project(project_dir)
        current_cost = 0.0
        try:
            aggregate = ledger.aggregate(project_id=slug)
            if isinstance(aggregate, dict):
                current_cost = float(aggregate.get("total_cost") or 0.0)
        except Exception:  # noqa: BLE001 — 失败安全
            current_cost = 0.0
        budget_limit = self._resolve_budget_limit(project_dir, slug)

        # ⑧ 团队状态 (按 agent 聚合)
        team_members = self._aggregate_team(team_state)

        # ⑨ 产品名 (product.json → ProductIntent.name; 缺失 → slug)
        product_id = self._load_product_name(project_dir, slug)

        # 汇总填充
        self.product_id = product_id or slug
        self.lifecycle_state = (
            str(state.lifecycle or state.status or "") if state is not None else ""
        )
        self.current_phase = phase
        self.current_task = current_task
        self.current_agent = current_agent
        self.team_members = team_members
        self.completed_tasks = completed
        self.total_tasks = total
        self.plan_version = plan_version
        self.replan_count = replan_count
        self.budget_limit = round(budget_limit, 6)
        self.current_cost = round(current_cost, 6)
        self.cost_percentage = (
            round(current_cost / budget_limit, 4) if budget_limit > 0 else 0.0
        )
        self.governance_status = governance_status
        self.governance_reason = governance_reason
        self.pending_review = pending_review
        self.updated_at = _now_iso()

    def _resolve_budget_limit(self, project_dir: Path, slug: str) -> float:
        """预算上限: 显式 budget 参数优先; 否则 project_budget.json; 缺失 → 0.0。"""
        budget = self._budget
        if isinstance(budget, (int, float)):
            return float(budget)
        if hasattr(budget, "max_total_cost"):
            return float(getattr(budget, "max_total_cost") or 0.0)
        if isinstance(budget, dict):
            return float(budget.get("max_total_cost") or 0.0)
        try:
            loaded = ProjectBudget.load(project_dir / PROJECT_BUDGET_FILE_NAME)
        except Exception:  # noqa: BLE001 — 失败安全
            loaded = None
        if loaded is not None:
            return float(loaded.max_total_cost or 0.0)
        return 0.0

    @staticmethod
    def _aggregate_team(team_state: dict[str, Any]) -> list[dict[str, Any]]:
        """team_execution_state.tasks → 按 agent 聚合 (角色/状态/计数)。"""
        tasks = team_state.get("tasks") or {}
        by_agent: dict[str, dict[str, Any]] = {}
        for entry in tasks.values():
            if not isinstance(entry, dict):
                continue
            agent = str(entry.get("agent") or "")
            status = str(entry.get("status") or "pending")
            if not agent:
                continue
            item = by_agent.setdefault(
                agent, {"agent": agent, "total": 0, "completed": 0, "running": 0}
            )
            item["total"] += 1
            if status == "completed":
                item["completed"] += 1
            if status == "running":
                item["running"] += 1
        members: list[dict[str, Any]] = []
        for agent, item in by_agent.items():
            total = item["total"]
            completed = item["completed"]
            if total and completed == total:
                member_status = "done"
            elif item["running"]:
                member_status = "active"
            else:
                member_status = "idle"
            members.append(
                {
                    "agent": agent,
                    "role": _agent_role(agent),
                    "status": member_status,
                    "total_tasks": total,
                    "completed_tasks": completed,
                }
            )
        members.sort(key=lambda m: _team_sort_key(m["role"]))
        return members

    @staticmethod
    def _load_product_name(project_dir: Path, slug: str) -> str:
        """product.json → 产品名 (缺失/损坏 → slug, 失败安全)。"""
        data = _read_json(project_dir / PRODUCT_FILE_NAME)
        if isinstance(data, dict):
            try:
                product = ProductIntent.from_dict(data)
                if product.name:
                    return str(product.name)
            except Exception:  # noqa: BLE001 — 失败安全
                pass
        return slug

    def _record_event(
        self, message: str, *, phase: str, task_id: str = "", agent_id: str = ""
    ) -> None:
        """追加生产事件 (内存 — 只读聚合, 不落盘)。"""
        event = ProductionEvent(
            timestamp=_now_iso(),
            phase=phase or self.current_phase,
            message=message,
            task_id=task_id,
            agent_id=agent_id,
            plan_version=int(self.plan_version or 1),
        )
        self.events.append(event)
        self.last_event = event

    # ------------------------------------------------------------ 只读视图

    def get_status(self) -> dict[str, Any]:
        """完整状态视图 (全部字段 — 渲染/审计用)。"""
        return {
            "project_id": self.project_id,
            "product_id": self.product_id,
            "lifecycle_state": self.lifecycle_state,
            "current_phase": self.current_phase,
            "current_task": self.current_task,
            "current_agent": self.current_agent,
            "team_members": [dict(m) for m in self.team_members],
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.total_tasks,
            "plan_version": self.plan_version,
            "replan_count": self.replan_count,
            "budget_limit": self.budget_limit,
            "current_cost": self.current_cost,
            "cost_percentage": self.cost_percentage,
            "governance_status": self.governance_status,
            "governance_reason": self.governance_reason,
            "pending_review": self.pending_review,
            "updated_at": self.updated_at,
        }

    def get_progress(self) -> float:
        """进度 (0-1: completed/total; 无任务 → 0.0)。"""
        if not self.total_tasks:
            return 0.0
        return round(self.completed_tasks / self.total_tasks, 4)

    def get_team_status(self) -> list[dict[str, Any]]:
        """团队各成员状态 (PM/Architect/Backend/Frontend/QA 聚合)。"""
        return [dict(m) for m in self.team_members]

    def get_cost_status(self) -> dict[str, Any]:
        """预算/成本状态。"""
        return {
            "budget_limit": self.budget_limit,
            "current_cost": self.current_cost,
            "cost_percentage": self.cost_percentage,
        }

    def get_governance_status(self) -> dict[str, Any]:
        """治理状态/原因。"""
        return {
            "status": self.governance_status,
            "reason": self.governance_reason,
        }

    def get_review(self) -> Optional[dict[str, Any]]:
        """待人工评审详情 (无 pending → None, 失败安全)。"""
        if not self.pending_review:
            return None
        try:
            gate = self._review_gate
            if gate is None:
                gate = ReviewGate.for_project(self._project_dir)
            for rec in gate.pending():
                ctx = rec.context or {}
                if ctx.get("project_id") != self.project_id:
                    continue
                return {
                    "review_id": rec.review_id,
                    "reason": rec.reason,
                    "trigger": rec.trigger,
                    "created_at": rec.created_at,
                    "estimated_cost": rec.estimated_cost,
                    "risk": rec.risk,
                    "affected_tasks": list(rec.affected_tasks),
                }
        except Exception:  # noqa: BLE001 — 失败安全
            return None
        return None

    # ------------------------------------------------------------ 刷新/视图

    def refresh(self, project_dir: Any) -> "ProductionSession":
        """重新聚合 (磁盘状态变更后调用; 保持注入的 ledger/gate/budget)。"""
        project_dir = Path(project_dir)
        self._project_dir = project_dir
        slug = self.project_id or str(project_dir.name)
        self._load_state(project_dir, slug)
        self._record_event("状态刷新", phase=self.current_phase)
        return self

    def view(self) -> dict[str, Any]:
        """统一用户视图 (to_markdown 数据源 — 用户可读口径)。"""
        team_line = " / ".join(
            f"{m['role']} {_team_mark(m['status'])}"
            for m in self.team_members
        )
        return {
            "project_id": self.project_id,
            "product_id": self.product_id,
            "phase": self.current_phase,
            "phase_label": PHASE_LABELS.get(self.current_phase, self.current_phase),
            "progress": self.get_progress(),
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.total_tasks,
            "plan_version": self.plan_version,
            "budget_limit": self.budget_limit,
            "current_cost": self.current_cost,
            "cost_percentage": self.cost_percentage,
            "team": team_line,
            "team_members": [dict(m) for m in self.team_members],
            "current_task": self.current_task,
            "current_agent": self.current_agent,
            "governance_status": self.governance_status,
            "governance_reason": self.governance_reason,
            "pending_review": self.pending_review,
            "lifecycle_state": self.lifecycle_state,
            "replan_count": self.replan_count,
            "updated_at": self.updated_at,
        }

    def to_markdown(self) -> str:
        """用户可读生产状态文本 (设计 §3 示例口径)。"""
        view = self.view()
        lines: list[str] = [
            view["product_id"] or view["project_id"] or "(未命名项目)",
            "",
            f"AI Team {view['phase_label']}",
            "",
        ]
        team_row = view["team"] or "无团队信息"
        lines.append(team_row)
        lines.append("")
        lines.append(f"任务: {view['completed_tasks']}/{view['total_tasks']}")
        lines.append("")
        lines.append(f"Plan Version: v{view['plan_version']}")
        lines.append("")
        if view["budget_limit"] > 0:
            lines.append(
                f"Budget: ${view['current_cost']:.2f} / ${view['budget_limit']:.2f}"
            )
        else:
            lines.append(f"Budget: ${view['current_cost']:.2f} (未设上限)")
        lines.append("")
        if view["current_task"]:
            agent = _agent_display(view["current_agent"]) or "AI"
            lines.append(f"当前: {agent} Agent 正在{view['current_task']}")
        else:
            lines.append("当前: 无进行中任务")
        lines.append("")
        if view["pending_review"]:
            review = self.get_review() or {}
            lines.append(f"待评审: {review.get('reason') or '需要人工评审'}")
            lines.append("")
        if view["governance_reason"]:
            lines.append(f"治理: {view['governance_reason']}")
            lines.append("")
        lines.append(f"状态: {view['phase'].upper()}")
        return "\n".join(lines)


def _team_mark(member_status: str) -> str:
    """成员状态 → 符号 (done=✓ / active=● / idle=○)。"""
    if member_status == "done":
        return _TEAM_MARK_DONE
    if member_status == "active":
        return _TEAM_MARK_ACTIVE
    return _TEAM_MARK_IDLE


def _team_sort_key(role: str) -> tuple[int, str]:
    """团队行排序键 (固定角色顺序; 未知角色排在末尾)。"""
    if role in TEAM_ROLE_ORDER:
        return (TEAM_ROLE_ORDER.index(role), role)
    return (len(TEAM_ROLE_ORDER), role)


__all__ = [
    "ProductionPhase",
    "ProductionEvent",
    "ProductionSession",
    "PHASE_LABELS",
    "TEAM_ROLE_ORDER",
    "_map_phase",
    "_agent_role",
    "_current_task_info",
    "_task_counts",
]
