"""factory-console/session/replanning.py — ReplanningEngine (S10-060 P1)。

Autonomous Replanning (设计 §2 P1): AI Team 观察/发现计划偏差 → 自己重新规划 →
修改任务图 → 继续生产。ReplanningEngine 消费 执行状态 / 计划 / 失败上下文 /
验证结果 / Agent 输出 / 依赖图 → 输出计划级决策 (KEEP_PLAN/REORDER_TASKS/
INSERT_TASK/MODIFY_TASK/BLOCK_TASK/SKIP_TASK/SPLIT_TASK/REQUEST_REVIEW +
reason), 落盘 replanning_decisions.json (append, 决策可解释性资产 — GAP G7)。

组件:
- ReplanDecision — 计划级决策模型 {decision, reason, affected_tasks, new_tasks,
  modified_tasks, dependency_changes, execution_order, plan_version, source_gap,
  timestamp} (+ to_dict/from_dict)
- ReplanningEngine — decide(...) 触发规则 (优先级从高到低):
    1. replan_count >= max_replan          → REQUEST_REVIEW (重规划超限)
    2. Agent 发现缺口 (missing/需要/缺少)   → INSERT_TASK (调用方 insert_tasks
       候选; 无候选但 gap_analysis 提供 → GapAnalyzer 结果驱动自动提案
       (TaskProposalEngine.propose + Validator — S10-061 批次 B); 无候选 →
       REQUEST_REVIEW); 候选依赖成环 → BLOCK_TASK (cyclic)
    3. 依赖不成立 (depends_on 任务被移除/不存在) → BLOCK_TASK
    4. 循环依赖信号 (cycle/cyclic/环)      → BLOCK_TASK (cyclic dependency)
    5. 任务不再需要 (obsolete/不再需要)    → SKIP_TASK
    6. 任务内容过时 (stale/过时/outdated)  → MODIFY_TASK (调用方 modified_tasks)
    7. 任务过大 (too large/过大)           → SPLIT_TASK (调用方 split_tasks)
    8. 前序结果改变 (reorder/重排)         → REORDER_TASKS (依赖图重算执行顺序)
    9. 无偏差                               → KEEP_PLAN (Repair 路径不变)
  record(decision) — append 落盘 replanning_decisions.json (失败安全);
  previous_decisions() — 读回 (失败安全 → [])

边界 (Repair vs Replanning 分离, 设计 §7 P6):
- Repair (quality.RepairManager): 当前任务失败 → retry — 任务级, 本模块不触碰
- Replanning (本模块): 计划不适合现实 → 改 DAG/计划 — 计划级
- 本模块只产出决策 + 可解释 reason, 不执行任务、不修改 workspace
  (执行侧决策消费在 orchestrator.ExecutionOrchestrator — P5 集成)
- 显式参数: insert_tasks/modified_tasks/split_tasks 为调用方提供的候选任务
  (设计: 不自动生成任务内容)

设计: docs/sprint10/S10-060-replanning-design.md §2 (P1) / §7 (P6)
边界:
- 纯标准库 (json/pathlib/datetime), 零模块依赖; 失败安全 (缺失/损坏 → 空记录, 永不抛)
- dependency_graph 鸭子类型: 仅需 cycle_detect(task, depends_on) / topological_order(tasks)
  (本仓库 TaskDependencyGraph 实现; 解耦避免循环依赖)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 缺省重规划决策资产文件 (~/.factory/teams/replanning_decisions.json — 设计 §4 资产口径;
#: 项目级决策记录 → projects/<slug>/replanning_decisions.json, 由调用方显式指定)
DEFAULT_REPLANNING_FILE = Path.home() / ".factory" / "teams" / "replanning_decisions.json"

#: 项目级重规划决策文件名 (projects/<slug>/replanning_decisions.json — S10-060 资产)
REPLANNING_DECISIONS_FILE_NAME = "replanning_decisions.json"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (决策时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReplanDecision:
    """计划级重规划决策 (设计 §2 P1 输出): 全字段 + to_dict/from_dict。

    decision:          8 决策之一 (KEEP_PLAN/REORDER_TASKS/INSERT_TASK/
                       MODIFY_TASK/BLOCK_TASK/SKIP_TASK/SPLIT_TASK/REQUEST_REVIEW)
    reason:            可解释原因 (为什么改变/不改变计划)
    affected_tasks:    受影响的计划任务 id 列表 (SKIP/BLOCK/SPLIT/MODIFY 目标)
    new_tasks:         新增任务候选 (INSERT_TASK/SPLIT_TASK — 调用方提供, 不自动生成)
    modified_tasks:    修改后的任务内容候选 (MODIFY_TASK — 调用方提供)
    dependency_changes: 依赖图变更记录 [{action, task, depends_on, reason}]
    execution_order:   重排后的执行顺序 (REORDER_TASKS — 依赖图拓扑序)
    plan_version:      决策时的计划版本 (v1/v2/v3 — 可回答"为什么改变计划")
    timestamp:         决策时间 (UTC ISO)
    """

    decision: str
    reason: str = ""
    affected_tasks: list[str] = field(default_factory=list)
    new_tasks: list[dict[str, Any]] = field(default_factory=list)
    modified_tasks: list[dict[str, Any]] = field(default_factory=list)
    dependency_changes: list[dict[str, Any]] = field(default_factory=list)
    execution_order: list[str] = field(default_factory=list)
    plan_version: int = 1
    # S10-061 批次 B: 触发缺口的 source_gap 标识 "{gap_type}@{source_task_id}"
    # (自动提案路径记录 — 同一 gap 防重 GAP G6 决策侧依据; 旧记录缺省 "")
    source_gap: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 replanning_decisions.json / 审计视图)。"""
        return {
            "decision": self.decision,
            "reason": self.reason,
            "affected_tasks": list(self.affected_tasks),
            "new_tasks": [dict(t) for t in self.new_tasks if isinstance(t, dict)],
            "modified_tasks": [
                dict(t) for t in self.modified_tasks if isinstance(t, dict)
            ],
            "dependency_changes": [
                dict(c) for c in self.dependency_changes if isinstance(c, dict)
            ],
            "execution_order": list(self.execution_order),
            "plan_version": int(self.plan_version or 1),
            "source_gap": str(self.source_gap or ""),
            "timestamp": self.timestamp or _now_iso(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ReplanDecision":
        """dict → ReplanDecision (缺失字段默认 — 前向兼容/失败安全)。"""
        if not isinstance(data, dict):
            return cls(decision="", reason="缺省决策 (空)")
        return cls(
            decision=str(data.get("decision") or ""),
            reason=str(data.get("reason") or ""),
            affected_tasks=[
                str(t) for t in (data.get("affected_tasks") or []) if not isinstance(t, dict)
            ],
            new_tasks=[
                dict(t) for t in (data.get("new_tasks") or []) if isinstance(t, dict)
            ],
            modified_tasks=[
                dict(t) for t in (data.get("modified_tasks") or []) if isinstance(t, dict)
            ],
            dependency_changes=[
                dict(c) for c in (data.get("dependency_changes") or []) if isinstance(c, dict)
            ],
            execution_order=[
                str(t) for t in (data.get("execution_order") or []) if not isinstance(t, dict)
            ],
            plan_version=int(data.get("plan_version") or 1),
            source_gap=str(data.get("source_gap") or ""),
            timestamp=str(data.get("timestamp") or ""),
        )


class ReplanningEngine:
    """自主重规划引擎 (S10-060 P1): 执行上下文 → 计划级决策 + 可解释 reason。

    decide(): 按优先级规则 (超限 → 缺口 → 依赖不成立 → 循环 → 过时 → 过时内容 →
    过大 → 重排 → KEEP_PLAN) 产出 ReplanDecision; 每次决策可 record 落盘
    replanning_decisions.json (append — 决策历史资产, 可解释性 G7)。
    record()/previous_decisions() 失败安全 (缺失/损坏 → 空)。

    与 HandoffDecisionEngine (S10-059, 执行级 7 决策) 的关系 (设计 §2):
    - HandoffDecisionEngine: 执行级 — 下一任务 CONTINUE/BLOCK/RETRY/REPAIR/...
    - ReplanningEngine:      计划级 — 计划是否适合现实, 需要时改 DAG/计划
    - 两者独立, 不混淆 (Repair 任务级 vs Replanning 计划级)
    """

    #: 8 计划级决策常量 (设计 §2 P1)
    DECISION_KEEP_PLAN = "KEEP_PLAN"
    DECISION_REORDER_TASKS = "REORDER_TASKS"
    DECISION_INSERT_TASK = "INSERT_TASK"
    DECISION_MODIFY_TASK = "MODIFY_TASK"
    DECISION_BLOCK_TASK = "BLOCK_TASK"
    DECISION_SKIP_TASK = "SKIP_TASK"
    DECISION_SPLIT_TASK = "SPLIT_TASK"
    DECISION_REQUEST_REVIEW = "REQUEST_REVIEW"

    #: 全部合法决策 (缺省回退 KEEP_PLAN — 失败安全)
    DECISIONS: tuple[str, ...] = (
        DECISION_KEEP_PLAN,
        DECISION_REORDER_TASKS,
        DECISION_INSERT_TASK,
        DECISION_MODIFY_TASK,
        DECISION_BLOCK_TASK,
        DECISION_SKIP_TASK,
        DECISION_SPLIT_TASK,
        DECISION_REQUEST_REVIEW,
    )

    #: 缺口信号 (Agent 输出含 → 计划缺口 → INSERT_TASK)
    GAP_MARKERS: tuple[str, ...] = ("missing", "需要", "缺少", "缺口", "not found")

    #: 任务不再需要信号 (→ SKIP_TASK)
    OBSOLETE_MARKERS: tuple[str, ...] = ("不再需要", "obsolete", "已过时", "不需要")

    #: 任务内容过时信号 (→ MODIFY_TASK)
    STALE_MARKERS: tuple[str, ...] = ("过时", "stale", "outdated", "已变更")

    #: 任务过大信号 (→ SPLIT_TASK)
    SPLIT_MARKERS: tuple[str, ...] = ("过大", "太大", "too large", "split")

    #: 顺序调整信号 (→ REORDER_TASKS)
    REORDER_MARKERS: tuple[str, ...] = ("reorder", "重排", "顺序调整", "先执行")

    #: 循环依赖信号 (→ BLOCK_TASK, reason=cyclic dependency)
    CYCLE_MARKERS: tuple[str, ...] = ("cycle", "cyclic", "循环依赖", "环")

    #: 项目级决策文件名 (projects/<slug>/replanning_decisions.json — S10-060 资产)
    FILE_NAME = REPLANNING_DECISIONS_FILE_NAME

    #: S10-061 批次 B — 自动提案安全边界 (设计 §7):
    #: auto_mode="auto_execute" 下 confidence < 该阈值 → 停止自主插入 (REQUEST_REVIEW)
    AUTO_EXECUTE_MIN_CONFIDENCE = 0.6

    #: 高风险严重度 (auto_mode="request_review" 下命中 → 停止自主插入)
    HIGH_RISK_SEVERITIES: tuple[str, ...] = ("high", "critical")

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else DEFAULT_REPLANNING_FILE

    # ------------------------------------------------------------ 决策

    def decide(
        self,
        execution_state: Optional[dict[str, Any]] = None,
        execution_plan: Optional[dict[str, Any]] = None,
        *,
        failures: Optional[list[dict[str, Any]]] = None,
        validation: Optional[dict[str, Any]] = None,
        agent_output: Optional[str] = None,
        dependency_graph: Any = None,
        workspace: Optional[dict[str, Any]] = None,
        max_replan: int = 5,
        plan_version: int = 1,
        replan_count: Optional[int] = None,
        insert_tasks: Optional[list[dict[str, Any]]] = None,
        modified_tasks: Optional[list[dict[str, Any]]] = None,
        split_tasks: Optional[list[dict[str, Any]]] = None,
        # S10-061 批次 B — 自动提案路径 (全部可选, 旧调用不变):
        gap_analysis: Any = None,
        task_proposal: Any = None,
        task_validator: Any = None,
        auto_mode: str = "auto_execute",
        max_auto_insert_tasks: int = 5,
        max_tasks_per_round: int = 3,
        max_total_generated_tasks: int = 10,
        generated_count: int = 0,
    ) -> ReplanDecision:
        """对失败/验证上下文产出计划级决策 (设计 §2 P1 规则, 优先级从高到低)。

        execution_state: 执行状态 dict ({plan_version?, replan_count?, tasks?});
        execution_plan:  执行计划 dict ({tasks: [{id, depends_on?}]});
        failures:        失败任务上下文 [{task_id, name, error}];
        validation:      验证结果 dict ({success?, errors?});
        agent_output:    Agent 输出文本 (缺口/过时/循环 信号来源);
        dependency_graph: 依赖图 (鸭子类型: cycle_detect/topological_order);
        workspace:       工作区上下文 (仅 reason 引用);
        max_replan:      重规划预算 (缺省 5 — 超过 → REQUEST_REVIEW);
        plan_version:    当前计划版本 (决策上下文);
        replan_count:    已执行重规划次数 (缺省从 execution_state 读);
        insert_tasks/modified_tasks/split_tasks: 调用方提供的候选任务
        (S10-060: 不自动生成任务内容 — 显式参数)。

        S10-061 批次 B (Autonomous Gap Resolution 集成, 设计 §6/§7):
        gap_analysis:    调用方已分析结果 (GapAnalysis/dict — GapAnalyzer 输出);
                         提供后: insert_tasks 为空 + 缺口建议 INSERT_TASK →
                         自动提案 (task_proposal.propose + task_validator.validate
                         → new_tasks, 非调用方注入);
        task_proposal:   提案引擎 (鸭子类型 propose(gap, existing_tasks, dag));
        task_validator:  提案验证器 (鸭子类型 validate(proposal, existing_tasks,
                         dag, replan_count, max_replan) → {valid, reasons});
        auto_mode:       安全边界 (缺省 "auto_execute"): auto_execute (高
                         confidence 自动执行; 低 confidence → REQUEST_REVIEW) /
                         auto_propose_review (生成提案但 REQUEST_REVIEW 待人工) /
                         request_review (高风险/低 confidence → REQUEST_REVIEW);
        max_auto_insert_tasks: 自动插入任务总数上限 (缺省 5, 防无限 GAP G5);
        max_tasks_per_round:   单轮自动提案上限 (缺省 3);
        max_total_generated_tasks: 本轮运行生成任务总数上限 (缺省 10);
        generated_count: 已自动生成任务数 (调用方累计 — 上限判定输入)。

        返回 ReplanDecision (全字段 + source_gap + timestamp)。
        """
        state = execution_state if isinstance(execution_state, dict) else {}
        plan = execution_plan if isinstance(execution_plan, dict) else {}
        failures = [f for f in (failures or []) if isinstance(f, dict)]
        validation = validation if isinstance(validation, dict) else {}
        insert_tasks = [t for t in (insert_tasks or []) if isinstance(t, dict)]
        modified_tasks = [t for t in (modified_tasks or []) if isinstance(t, dict)]
        split_tasks = [t for t in (split_tasks or []) if isinstance(t, dict)]
        output = str(agent_output or "")
        cur_version = int(state.get("plan_version") or plan_version or 1)
        cur_replan = (
            int(replan_count)
            if replan_count is not None
            else int(state.get("replan_count") or 0)
        )
        plan_tasks = [t for t in (plan.get("tasks") or []) if isinstance(t, dict)]
        plan_ids = {str(t.get("id")) for t in plan_tasks if t.get("id")}
        failed_ids = [str(f.get("task_id") or "") for f in failures if f.get("task_id")]

        # ---- 规则 1: 重规划次数超限 → REQUEST_REVIEW (防无限循环, 设计 §5 P4)
        if cur_replan >= int(max_replan):
            return self._decision(
                self.DECISION_REQUEST_REVIEW,
                reason=(
                    f"重规划次数超限: replan_count={cur_replan} >= "
                    f"max_replan={max_replan} — 需要人工评审, 停止自主重规划 "
                    f"(REQUEST_REVIEW)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
            )

        # ---- 规则 2: Agent 发现计划缺口 (missing/需要/缺少) → INSERT_TASK
        gap = any(m in output.lower() for m in self.GAP_MARKERS)
        # S10-060 修复: "不再需要" 含 "需要" (GAP 子串) → 误判缺口;
        # SKIP 信号 (不再需要/obsolete) 优先于缺口 (任务不要了无需插入新任务)
        if "不再" in output and "需要" in output:
            gap = False
        # S10-061 批次 B: gap_analysis 建议 INSERT_TASK → 同样视为缺口
        # (GapAnalyzer 信号面更广 — 如 "依赖缺失" 不命中 GAP_MARKERS 但分析检出)
        ga = self._as_analysis(gap_analysis)
        ga_insert = bool(
            ga
            and ga.get("detected")
            and ga.get("recommended_action") == self.DECISION_INSERT_TASK
        )
        gap = gap or ga_insert
        if gap:
            if insert_tasks:
                # 候选新任务依赖成环 → 拒绝插入 → BLOCK_TASK (cyclic dependency)
                cyclic = self._candidate_cycle(
                    dependency_graph, insert_tasks
                )
                if cyclic is not None:
                    return self._decision(
                        self.DECISION_BLOCK_TASK,
                        reason=(
                            f"新任务依赖形成循环: {cyclic[0]} → {cyclic[1]} — "
                            f"拒绝插入 (cyclic dependency — BLOCK_TASK)"
                        ),
                        affected_tasks=failed_ids,
                        plan_version=cur_version,
                    )
                return self._decision(
                    self.DECISION_INSERT_TASK,
                    reason=(
                        f"Agent 发现计划缺口 ({self._marker_hit(output, self.GAP_MARKERS)}): "
                        f"计划缺 {len(insert_tasks)} 个任务, 插入后继续执行 "
                        f"(INSERT_TASK)"
                    ),
                    affected_tasks=failed_ids,
                    new_tasks=insert_tasks,
                    plan_version=cur_version,
                )
            if ga and ga.get("detected"):
                # 自动提案路径 (S10-061 批次 B): 缺口分析结果驱动 — 建议动作
                # 分发 + TaskProposalEngine.propose + Validator + 上限/auto_mode
                room = max(
                    0,
                    min(
                        int(max_auto_insert_tasks or 5),
                        int(max_total_generated_tasks or 10),
                    )
                    - int(generated_count or 0),
                )
                return self._gap_analysis_decision(
                    ga=ga,
                    source_gap=self._source_gap(ga),
                    failed_ids=failed_ids,
                    cur_version=cur_version,
                    plan_tasks=plan_tasks,
                    dependency_graph=dependency_graph,
                    task_proposal=task_proposal,
                    task_validator=task_validator,
                    cur_replan=cur_replan,
                    max_replan=max_replan,
                    auto_mode=str(auto_mode or "auto_execute"),
                    max_tasks_per_round=int(max_tasks_per_round or 3),
                    room=room,
                )
            return self._decision(
                self.DECISION_REQUEST_REVIEW,
                reason=(
                    f"Agent 发现计划缺口 ({self._marker_hit(output, self.GAP_MARKERS)}) "
                    f"但无新任务候选 (insert_tasks 为空) — 需人工提供缺失任务 "
                    f"(REQUEST_REVIEW)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
            )

        # ---- 规则 3: 依赖不成立 (depends_on 任务被移除/不存在) → BLOCK_TASK
        missing = self._missing_deps(plan, dependency_graph, failed_ids)
        if missing:
            return self._decision(
                self.DECISION_BLOCK_TASK,
                reason=(
                    f"依赖不成立: 任务 {missing[0]['task']} 依赖的 "
                    f"{', '.join(missing[0]['deps'])} 不存在/已被移除 — "
                    f"阻塞该任务 (BLOCK_TASK)"
                ),
                affected_tasks=[missing[0]["task"]],
                plan_version=cur_version,
            )

        # ---- 规则 4: 循环依赖信号 → BLOCK_TASK (cyclic dependency)
        if any(m in output.lower() for m in self.CYCLE_MARKERS):
            return self._decision(
                self.DECISION_BLOCK_TASK,
                reason=(
                    f"检测到循环依赖: {self._marker_hit(output, self.CYCLE_MARKERS)} "
                    f"— 拒绝计划变更 (cyclic dependency — BLOCK_TASK)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
            )

        # ---- 规则 5: 任务不再需要 (obsolete) → SKIP_TASK
        obsolete = self._obsolete_signal(output, validation)
        if obsolete:
            return self._decision(
                self.DECISION_SKIP_TASK,
                reason=(
                    f"任务不再需要 ({obsolete}): 计划任务过时/被取代 — "
                    f"跳过该任务 (SKIP_TASK)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
            )

        # ---- 规则 6: 任务内容过时 → MODIFY_TASK
        if any(m in output.lower() for m in self.STALE_MARKERS):
            return self._decision(
                self.DECISION_MODIFY_TASK,
                reason=(
                    f"任务内容过时 ({self._marker_hit(output, self.STALE_MARKERS)}): "
                    f"需修改任务内容后继续 (MODIFY_TASK)"
                ),
                affected_tasks=failed_ids,
                modified_tasks=modified_tasks,
                plan_version=cur_version,
            )

        # ---- 规则 7: 任务过大 → SPLIT_TASK
        if any(m in output.lower() for m in self.SPLIT_MARKERS):
            return self._decision(
                self.DECISION_SPLIT_TASK,
                reason=(
                    f"任务过大 ({self._marker_hit(output, self.SPLIT_MARKERS)}): "
                    f"拆分为 {len(split_tasks) or '若干'} 个子任务 (SPLIT_TASK)"
                ),
                affected_tasks=failed_ids,
                new_tasks=split_tasks,
                plan_version=cur_version,
            )

        # ---- 规则 8: 前序结果改变 → REORDER_TASKS (依赖图重算执行顺序)
        if any(m in output.lower() for m in self.REORDER_MARKERS):
            order = self._execution_order(dependency_graph, plan_ids)
            return self._decision(
                self.DECISION_REORDER_TASKS,
                reason=(
                    f"前序结果改变 ({self._marker_hit(output, self.REORDER_MARKERS)}): "
                    f"重算依赖拓扑, 调整执行顺序 (REORDER_TASKS)"
                ),
                affected_tasks=failed_ids,
                execution_order=order,
                plan_version=cur_version,
            )

        # ---- 规则 9: 无偏差 → KEEP_PLAN (Repair 路径不变 — 任务级修复独立)
        return self._decision(
            self.DECISION_KEEP_PLAN,
            reason=(
                f"未发现计划偏差 (失败 {len(failures)} 个任务, 无缺口/循环/过时信号); "
                f"计划保持不变, 任务级失败由 Repair 处理 (KEEP_PLAN)"
            ),
            affected_tasks=failed_ids,
            plan_version=cur_version,
        )

    # ------------------------------------------------------------ 记录/读回

    def record(self, decision: Any) -> dict[str, Any]:
        """append 落盘 replanning_decisions.json (失败安全: 读写异常 → 不抛)。"""
        obj = self._normalize(decision)
        records = self.previous_decisions()
        records.append(obj)
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断决策流
            pass
        return obj

    def previous_decisions(self) -> list[dict[str, Any]]:
        """读回全部重规划决策记录 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [
                    self._normalize(d) for d in data if isinstance(d, dict)
                ]
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空记录
            pass
        return []

    def decisions_for(self, task_id: str) -> list[dict[str, Any]]:
        """某任务相关的全部历史重规划决策 (affected_tasks 含 task_id)。"""
        key = str(task_id)
        return [
            d
            for d in self.previous_decisions()
            if key in (d.get("affected_tasks") or [])
        ]

    def decisions_file(self) -> Path:
        """当前落盘文件路径。"""
        return Path(self._file)

    # ------------------------------------------------------------ 内部

    @classmethod
    def _normalize(cls, decision: Any) -> dict[str, Any]:
        """ReplanDecision/dict → 归一化 dict (缺失字段失败安全缺省; 未知决策 → KEEP_PLAN)。"""
        if isinstance(decision, ReplanDecision):
            decision = decision.to_dict()
        if not isinstance(decision, dict):
            return cls._decision(cls.DECISION_KEEP_PLAN, reason="缺省决策 (空)").to_dict()
        name = str(decision.get("decision") or cls.DECISION_KEEP_PLAN)
        if name not in cls.DECISIONS:
            name = cls.DECISION_KEEP_PLAN
        return {
            "decision": name,
            "reason": str(decision.get("reason") or ""),
            "affected_tasks": [
                str(t)
                for t in (decision.get("affected_tasks") or [])
                if not isinstance(t, dict)
            ],
            "new_tasks": [
                dict(t) for t in (decision.get("new_tasks") or []) if isinstance(t, dict)
            ],
            "modified_tasks": [
                dict(t) for t in (decision.get("modified_tasks") or []) if isinstance(t, dict)
            ],
            "dependency_changes": [
                dict(c)
                for c in (decision.get("dependency_changes") or [])
                if isinstance(c, dict)
            ],
            "execution_order": [
                str(t)
                for t in (decision.get("execution_order") or [])
                if not isinstance(t, dict)
            ],
            "plan_version": int(decision.get("plan_version") or 1),
            "source_gap": str(decision.get("source_gap") or ""),
            "timestamp": str(decision.get("timestamp") or _now_iso()),
        }

    @classmethod
    def _decision(
        cls,
        decision: str,
        *,
        reason: str = "",
        affected_tasks: Optional[list[str]] = None,
        new_tasks: Optional[list[dict[str, Any]]] = None,
        modified_tasks: Optional[list[dict[str, Any]]] = None,
        execution_order: Optional[list[str]] = None,
        plan_version: int = 1,
        source_gap: str = "",
    ) -> ReplanDecision:
        """组装 ReplanDecision (全字段 + source_gap + timestamp)。"""
        return ReplanDecision(
            decision=decision,
            reason=reason,
            affected_tasks=list(affected_tasks or []),
            new_tasks=[dict(t) for t in (new_tasks or []) if isinstance(t, dict)],
            modified_tasks=[
                dict(t) for t in (modified_tasks or []) if isinstance(t, dict)
            ],
            execution_order=list(execution_order or []),
            plan_version=int(plan_version or 1),
            source_gap=str(source_gap or ""),
            timestamp=_now_iso(),
        )

    @staticmethod
    def _marker_hit(output: str, markers: tuple[str, ...]) -> str:
        """输出中命中的首个信号词 (lower 匹配 — reason 可读)。"""
        low = str(output or "").lower()
        for m in markers:
            if m in low:
                return m
        return ""

    @classmethod
    def _missing_deps(
        cls,
        plan: dict[str, Any],
        graph: Any,
        failed_ids: list[str],
    ) -> list[dict[str, Any]]:
        """失败任务中依赖不存在/被移除的任务 (规则 3)。

        依赖来源: 依赖图 (graph.get(task_id)) 或 计划任务 depends_on;
        依赖目标不在计划任务 id 集合 → 依赖不成立。
        """
        plan_tasks = [t for t in (plan.get("tasks") or []) if isinstance(t, dict)]
        plan_ids = {str(t.get("id")) for t in plan_tasks if t.get("id")}
        task_deps: dict[str, list[str]] = {}
        for t in plan_tasks:
            tid = str(t.get("id") or "")
            if not tid:
                continue
            deps: list[str] = []
            try:
                deps = list(graph.get(tid) or []) if graph is not None else []
            except Exception:  # noqa: BLE001 — 失败安全: 图查询异常 → 空
                deps = []
            if not deps:
                deps = [
                    str(d)
                    for d in (t.get("depends_on") or [])
                    if not isinstance(d, dict)
                ]
            task_deps[tid] = deps
        result: list[dict[str, Any]] = []
        for tid in failed_ids:
            missing = [
                d for d in task_deps.get(tid, []) if d and d not in plan_ids
            ]
            if missing:
                result.append({"task": tid, "deps": missing})
        return result

    @classmethod
    def _candidate_cycle(cls, graph: Any, candidates: list[dict[str, Any]]) -> Optional[list[str]]:
        """候选新任务中会形成环的依赖边 (规则 2 前置检查)。

        对每个候选任务与其 depends_on: 图中已存在 task → ... → depends_on
        路径 (即新边 depends_on → task 会成环) → 返回 [task, depends_on]。
        """
        if graph is None:
            return None
        for cand in candidates:
            tid = str(cand.get("id") or "")
            for d in cand.get("depends_on") or []:
                if isinstance(d, dict):
                    continue
                dep = str(d)
                if not tid or not dep:
                    continue
                try:
                    if graph.cycle_detect(tid, dep):
                        return [tid, dep]
                except Exception:  # noqa: BLE001 — 失败安全: 无 cycle_detect → 跳过
                    return None
        return None

    @classmethod
    def _obsolete_signal(cls, output: str, validation: dict[str, Any]) -> str:
        """过时信号: Agent 输出 or 验证结果 errors (规则 5)。"""
        hit = cls._marker_hit(output, cls.OBSOLETE_MARKERS)
        if hit:
            return hit
        errors = validation.get("errors") or []
        if isinstance(errors, list):
            joined = " ".join(str(e) for e in errors if e is not None)
            hit = cls._marker_hit(joined, cls.OBSOLETE_MARKERS)
            if hit:
                return hit
        reason = str(validation.get("reason") or validation.get("message") or "")
        return cls._marker_hit(reason, cls.OBSOLETE_MARKERS)

    @classmethod
    def _execution_order(cls, graph: Any, plan_ids: set[str]) -> list[str]:
        """依赖图拓扑序 (规则 8); 无图/异常 → 计划原顺序 (失败安全)。"""
        if graph is None or not plan_ids:
            return list(plan_ids)
        try:
            return [str(t) for t in graph.topological_order(list(plan_ids))]
        except Exception:  # noqa: BLE001 — 失败安全: 拓扑异常 → 原顺序
            return list(plan_ids)

    # ------------------------------------------------------------ S10-061 自动提案

    @staticmethod
    def _as_analysis(gap_analysis: Any) -> Optional[dict[str, Any]]:
        """GapAnalysis/dict → 归一化 dict (字段缺省失败安全; 非法 → None)。"""
        if gap_analysis is None:
            return None
        if hasattr(gap_analysis, "to_dict"):
            try:
                gap_analysis = gap_analysis.to_dict()
            except Exception:  # noqa: BLE001 — 失败安全: 转换异常 → 无分析
                return None
        if not isinstance(gap_analysis, dict):
            return None
        return {
            "detected": bool(gap_analysis.get("detected")),
            "gap_type": str(gap_analysis.get("gap_type") or ""),
            "source_task_id": str(gap_analysis.get("source_task_id") or ""),
            "severity": str(gap_analysis.get("severity") or "low"),
            "confidence": float(gap_analysis.get("confidence") or 0.0),
            "recommended_action": str(
                gap_analysis.get("recommended_action") or "NO_ACTION"
            ),
            "description": str(gap_analysis.get("description") or ""),
        }

    @staticmethod
    def _source_gap(ga: dict[str, Any]) -> str:
        """缺口唯一标识 "{gap_type}@{source_task_id}" (无来源 → 仅 gap_type)。"""
        gtype = str(ga.get("gap_type") or "")
        if not gtype:
            return ""
        sid = str(ga.get("source_task_id") or "")
        return f"{gtype}@{sid}" if sid else gtype

    def _gap_analysis_decision(
        self,
        *,
        ga: dict[str, Any],
        source_gap: str,
        failed_ids: list[str],
        cur_version: int,
        plan_tasks: list[dict[str, Any]],
        dependency_graph: Any,
        task_proposal: Any,
        task_validator: Any,
        cur_replan: int,
        max_replan: int,
        auto_mode: str,
        max_tasks_per_round: int,
        room: int,
    ) -> ReplanDecision:
        """缺口分析结果 → 决策 (S10-061 批次 B): 建议动作分发 + 自动提案 +
        安全边界 (auto_mode) + 防无限上限 (GAP G5/G6/G7)。"""
        gtype = str(ga.get("gap_type") or "unknown")
        conf = float(ga.get("confidence") or 0.0)
        sev = str(ga.get("severity") or "low")
        action = str(ga.get("recommended_action") or "NO_ACTION")
        who = source_gap or gtype

        # 非 INSERT 建议: 人工评审类 → REQUEST_REVIEW; 修复类 → KEEP_PLAN
        # (Repair 路径不变 — 计划级不介入任务级修复)
        if action != self.DECISION_INSERT_TASK:
            if action in (self.DECISION_REQUEST_REVIEW, "BLOCK"):
                return self._decision(
                    self.DECISION_REQUEST_REVIEW,
                    reason=(
                        f"Gap 分析建议 {action} ({who}, confidence={conf:.2f}) "
                        f"— 高风险/需人工评审 (REQUEST_REVIEW)"
                    ),
                    affected_tasks=failed_ids,
                    plan_version=cur_version,
                    source_gap=source_gap,
                )
            return self._decision(
                self.DECISION_KEEP_PLAN,
                reason=(
                    f"Gap 分析建议 {action} ({who}) — 任务级 Repair 路径处理, "
                    f"计划不变 (KEEP_PLAN)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
                source_gap=source_gap,
            )

        # ---- INSERT_TASK: auto_mode 安全边界 (设计 §7)
        if auto_mode == "request_review" and (
            sev in self.HIGH_RISK_SEVERITIES or conf < self.AUTO_EXECUTE_MIN_CONFIDENCE
        ):
            return self._decision(
                self.DECISION_REQUEST_REVIEW,
                reason=(
                    f"auto_mode=request_review: {who} severity={sev}/"
                    f"confidence={conf:.2f} — 高风险/低 confidence, 停止自主插入 "
                    f"(REQUEST_REVIEW)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
                source_gap=source_gap,
            )
        if auto_mode == "auto_propose_review":
            proposals = self._generate_proposals(
                ga=ga,
                plan_tasks=plan_tasks,
                dependency_graph=dependency_graph,
                task_proposal=task_proposal,
                task_validator=task_validator,
                cur_replan=cur_replan,
                max_replan=max_replan,
                max_tasks_per_round=max_tasks_per_round,
                room=room,
            )
            if not proposals:
                return self._decision(
                    self.DECISION_REQUEST_REVIEW,
                    reason=(
                        f"Gap {who} 无有效任务提案 (无模板/验证未通过/上限已到) — "
                        f"需人工评审 (REQUEST_REVIEW)"
                    ),
                    affected_tasks=failed_ids,
                    plan_version=cur_version,
                    source_gap=source_gap,
                )
            return self._decision(
                self.DECISION_REQUEST_REVIEW,
                reason=(
                    f"auto_mode=auto_propose_review: {who} 已生成 {len(proposals)} "
                    f"个任务提案 (task_proposals.json), 需人工评审后执行 "
                    f"(REQUEST_REVIEW)"
                ),
                affected_tasks=failed_ids,
                new_tasks=proposals,
                plan_version=cur_version,
                source_gap=source_gap,
            )
        # auto_execute (缺省)
        if conf < self.AUTO_EXECUTE_MIN_CONFIDENCE:
            return self._decision(
                self.DECISION_REQUEST_REVIEW,
                reason=(
                    f"低 confidence ({conf:.2f} < "
                    f"{self.AUTO_EXECUTE_MIN_CONFIDENCE}) — 停止自主插入, "
                    f"需人工评审 (REQUEST_REVIEW)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
                source_gap=source_gap,
            )
        proposals = self._generate_proposals(
            ga=ga,
            plan_tasks=plan_tasks,
            dependency_graph=dependency_graph,
            task_proposal=task_proposal,
            task_validator=task_validator,
            cur_replan=cur_replan,
            max_replan=max_replan,
            max_tasks_per_round=max_tasks_per_round,
            room=room,
        )
        if not proposals:
            return self._decision(
                self.DECISION_REQUEST_REVIEW,
                reason=(
                    f"Gap {who} 无有效任务提案 (无模板/验证未通过/上限已到) — "
                    f"需人工评审 (REQUEST_REVIEW)"
                ),
                affected_tasks=failed_ids,
                plan_version=cur_version,
                source_gap=source_gap,
            )
        return self._decision(
            self.DECISION_INSERT_TASK,
            reason=(
                f"Gap 分析检出 {who} (confidence={conf:.2f}): 自动生成 "
                f"{len(proposals)} 个任务提案, 插入后继续执行 (INSERT_TASK)"
            ),
            affected_tasks=failed_ids,
            new_tasks=proposals,
            plan_version=cur_version,
            source_gap=source_gap,
        )

    def _generate_proposals(
        self,
        *,
        ga: dict[str, Any],
        plan_tasks: list[dict[str, Any]],
        dependency_graph: Any,
        task_proposal: Any,
        task_validator: Any,
        cur_replan: int,
        max_replan: int,
        max_tasks_per_round: int,
        room: int,
    ) -> list[dict[str, Any]]:
        """缺口 → 任务提案 (TaskProposalEngine.propose + Validator 验证门)。

        返回插入候选 dict 列表 (含 id/name/depends_on 插入面 + 提案元数据);
        上限: min(max_tasks_per_round, room) — 防无限 (GAP G5); 失败安全:
        引擎/验证器异常 → 空列表 (REQUEST_REVIEW 路径)。
        """
        if task_proposal is None or room <= 0:
            return []
        try:
            proposed = task_proposal.propose(ga, plan_tasks, dependency_graph)
        except Exception:  # noqa: BLE001 — 失败安全: 提案异常 → 无提案
            return []
        items: list[Any] = []
        if isinstance(proposed, list):
            items = [p for p in proposed if p is not None]
        elif proposed is not None:
            items = [proposed]
        out: list[dict[str, Any]] = []
        for p in items:
            d = p.to_dict() if hasattr(p, "to_dict") else (dict(p) if isinstance(p, dict) else None)
            if not isinstance(d, dict):
                continue
            if task_validator is not None:
                try:
                    vres = task_validator.validate(
                        p, plan_tasks, dependency_graph, cur_replan, max_replan
                    )
                except Exception:  # noqa: BLE001 — 失败安全: 验证异常 → 拒绝
                    vres = {"valid": False, "reasons": ["validator 异常"]}
                if not (vres or {}).get("valid"):
                    continue
            d = {
                **d,
                # 插入面 (orchestrator._insert_tasks 消费): id/name/depends_on
                "id": str(d.get("task_id") or d.get("id") or ""),
                "name": str(d.get("title") or d.get("name") or ""),
                "depends_on": [
                    str(x)
                    for x in (d.get("dependencies") or d.get("depends_on") or [])
                    if not isinstance(x, dict)
                ],
            }
            if not d["id"]:
                continue
            out.append(d)
            if len(out) >= max(1, int(max_tasks_per_round or 1)):
                break
        return out[: max(0, int(room))]
