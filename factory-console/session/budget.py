"""factory-console/session/budget.py — ProjectBudget + BudgetUsage + BudgetEnforcer (S10-063 批次 A + S10-065 批次 C)。

Production Governance (GAP G1/G2, 设计 §2-§3): 项目级总预算模型 + 执行闸。
- ProjectBudget — 总预算 (token/cost/calls/replans/retries/repairs/task_count/
  execution_time/concurrent_agents + warn/review 比例; 0=无限, 但
  max_replans=5 / max_retries=1 / max_repairs=2 / max_concurrent_agents=1 有缺省值)
- BudgetUsage    — 已消耗量 (from_records 从 CostRecord 列表聚合) + spent/
  remaining/ratio (消耗比 — 取所有有界维度最高值, 无界维度不参与);
  execution_time 维度 (S10-065): from_records 聚合 sum(latency),
  orchestrator _GovernanceContext._usage 以 wall-clock elapsed 覆盖
  (max 取大 — 执行时间维度真正生效, GAP G7)
- BudgetEnforcer — check(budget, usage) → {level: ok|warn|review|block, reason,
  usage, ratio}: 80%→WARN (继续) / 90%→REVIEW (停止等审批) / 100%→BLOCK (禁止);
  enforce(budget, usage, action) → {allowed, level, reason}: 任何 action
  (llm/execute/retry/repair/replan/new_task) 在 block 级一律 allowed=False。

失败安全: save (目录不可写等 → 不抛) / load (缺失/损坏 → None/默认) /
from_dict (缺失字段 → 缺省值, 前向兼容)。

设计: docs/sprint10/S10-063-production-governance-design.md §2-§3
边界: 纯标准库 (json/pathlib/dataclasses/datetime), 零依赖, 不修改任何现有模块;
本模块只判定, 不执行动作 (执行侧接入在后续批次)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: 缺省预算资产文件 (~/.factory/cost/project_budget.json — 与 cost ledger 同空间;
#: 项目级预算 → projects/<slug>/project_budget.json, 由调用方显式指定)
DEFAULT_BUDGET_FILE = Path.home() / ".factory" / "cost" / "project_budget.json"

#: 项目级预算文件名 (projects/<slug>/project_budget.json)
PROJECT_BUDGET_FILE_NAME = "project_budget.json"

#: 缺省告警比例 (80% → WARN, 继续执行)
DEFAULT_WARN_RATIO = 0.8

#: 缺省评审比例 (90% → REVIEW, 停止等审批)
DEFAULT_REVIEW_RATIO = 0.9

#: BudgetEnforcer 支持的 action 白名单 (enforce 判定用 — 未知 action 宽松处理)
ENFORCE_ACTIONS: tuple[str, ...] = (
    "llm", "execute", "retry", "repair", "replan", "new_task",
)


@dataclass
class ProjectBudget:
    """项目级总预算 (设计 §2): 全字段 + to_dict/from_dict/save/load (失败安全)。

    0 = 无限 (该维度不设上限, 不参与消耗比计算); 例外缺省值:
    max_replans=5 / max_retries=1 / max_repairs=2 / max_concurrent_agents=1。
    warn_ratio / review_ratio — BudgetEnforcer 三档闸门比例 (0.8/0.9)。
    """

    max_total_tokens: int = 0
    max_total_cost: float = 0.0
    max_llm_calls: int = 0
    max_replans: int = 5
    max_retries: int = 1
    max_repairs: int = 2
    max_task_count: int = 0
    max_execution_time: float = 0.0
    max_concurrent_agents: int = 1
    warn_ratio: float = DEFAULT_WARN_RATIO
    review_ratio: float = DEFAULT_REVIEW_RATIO

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 project_budget.json / 审计视图)。"""
        return {
            "max_total_tokens": int(self.max_total_tokens),
            "max_total_cost": float(self.max_total_cost),
            "max_llm_calls": int(self.max_llm_calls),
            "max_replans": int(self.max_replans),
            "max_retries": int(self.max_retries),
            "max_repairs": int(self.max_repairs),
            "max_task_count": int(self.max_task_count),
            "max_execution_time": float(self.max_execution_time),
            "max_concurrent_agents": int(self.max_concurrent_agents),
            "warn_ratio": float(self.warn_ratio),
            "review_ratio": float(self.review_ratio),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ProjectBudget":
        """dict → ProjectBudget (缺失字段 → 缺省值, 前向兼容/失败安全)。"""
        if not isinstance(data, dict):
            return cls()
        return cls(
            max_total_tokens=int(data.get("max_total_tokens") or 0),
            max_total_cost=float(data.get("max_total_cost") or 0.0),
            max_llm_calls=int(data.get("max_llm_calls") or 0),
            max_replans=int(data.get("max_replans") or 5),
            max_retries=int(data.get("max_retries") or 1),
            max_repairs=int(data.get("max_repairs") or 2),
            max_task_count=int(data.get("max_task_count") or 0),
            max_execution_time=float(data.get("max_execution_time") or 0.0),
            max_concurrent_agents=int(data.get("max_concurrent_agents") or 1),
            warn_ratio=float(data.get("warn_ratio") or DEFAULT_WARN_RATIO),
            review_ratio=float(data.get("review_ratio") or DEFAULT_REVIEW_RATIO),
        )

    def save(self, file: Any = None) -> None:
        """落盘 (失败安全: 读写异常 → 不抛, 调用流不中断)。"""
        path = Path(file) if file is not None else DEFAULT_BUDGET_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    @classmethod
    def load(cls, file: Any = None) -> Optional["ProjectBudget"]:
        """读回 (失败安全: 缺失/损坏 → None; 成功 → ProjectBudget)。"""
        path = Path(file) if file is not None else DEFAULT_BUDGET_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:  # noqa: BLE001 — 缺失/损坏 → None
            return None

    @classmethod
    def load_or_default(cls, file: Any = None) -> "ProjectBudget":
        """读回, 缺失/损坏 → 缺省预算 (调用方无感, 失败安全)。"""
        budget = cls.load(file)
        return budget if budget is not None else cls()


@dataclass
class BudgetUsage:
    """已消耗量 (设计 §2): 从 CostRecord 列表聚合 (from_records)。

    spent — 已花成本 (USD); ratio — 消耗比 (取所有有界维度最高值,
    与 budget 比较; 无预算维度不参与); remaining — 剩余预算比例 (1 - ratio)。
    _budget — 可选绑定预算 (from_records(records, budget=...) 注入,
    供 ratio/spent/remaining 属性使用; 无绑定 → ratio=0.0)。
    """

    total_tokens: int = 0
    total_cost: float = 0.0
    llm_calls: int = 0
    replans: int = 0
    retries: int = 0
    repairs: int = 0
    task_count: int = 0
    execution_time: float = 0.0
    concurrent_agents: int = 0
    _budget: Optional["ProjectBudget"] = field(default=None, repr=False)

    # ------------------------------------------------------------ 属性

    @property
    def spent(self) -> float:
        """已花成本 (USD) — 成本维度为主。"""
        return float(self.total_cost)

    @property
    def ratio(self) -> float:
        """消耗比 (绑定预算时 = ratio_with(budget); 未绑定 → 0.0)。"""
        if self._budget is None:
            return 0.0
        return self.ratio_with(self._budget)

    @property
    def remaining(self) -> float:
        """剩余预算比例 (0..1; 无消耗 → 1.0)。"""
        return max(0.0, 1.0 - self.ratio)

    def ratio_with(self, budget: Any) -> float:
        """对给定预算计算消耗比 — 取所有有界维度 (limit>0) 的最高值。

        所有维度均 0 (无限) → 0.0 (无消耗比, check 判 ok)。
        """
        ratios: list[float] = []
        if budget.max_total_tokens > 0:
            ratios.append(self.total_tokens / budget.max_total_tokens)
        if budget.max_total_cost > 0:
            ratios.append(self.total_cost / budget.max_total_cost)
        if budget.max_llm_calls > 0:
            ratios.append(self.llm_calls / budget.max_llm_calls)
        if budget.max_replans > 0:
            ratios.append(self.replans / budget.max_replans)
        if budget.max_retries > 0:
            ratios.append(self.retries / budget.max_retries)
        if budget.max_repairs > 0:
            ratios.append(self.repairs / budget.max_repairs)
        if budget.max_task_count > 0:
            ratios.append(self.task_count / budget.max_task_count)
        if budget.max_execution_time > 0:
            ratios.append(self.execution_time / budget.max_execution_time)
        if budget.max_concurrent_agents > 0:
            ratios.append(self.concurrent_agents / budget.max_concurrent_agents)
        return max(ratios) if ratios else 0.0

    # ------------------------------------------------------------ 聚合

    @classmethod
    def from_records(
        cls, records: Any, budget: Optional["ProjectBudget"] = None
    ) -> "BudgetUsage":
        """从 CostRecord dict 列表聚合消耗量 (失败安全: 非列表/坏项 → 忽略)。

        total_tokens — sum(total_tokens, 缺省 input+output);
        total_cost   — sum(estimated_cost);
        llm_calls    — 记录条数 (每条 CostRecord = 一次 LLM 调用);
        replans      — purpose == REPLANNING 条数;
        repairs      — purpose == REPAIR 条数;
        retries      — purpose == RETRY 或 kind == retry 条数 (宽松兼容);
        task_count   — 去重 task_id 数; concurrent_agents — 去重 agent_id 数;
        execution_time — sum(latency)。
        """
        if not isinstance(records, list):
            records = []
        total_cost = 0.0
        total_tokens = 0
        calls = 0
        replans = repairs = retries = 0
        tasks: set[str] = set()
        agents: set[str] = set()
        exec_time = 0.0
        for rec in records:
            if not isinstance(rec, dict):
                continue
            calls += 1
            total_cost += float(rec.get("estimated_cost") or 0.0)
            tok = int(rec.get("total_tokens") or 0)
            if tok <= 0:
                tok = int(rec.get("input_tokens") or 0) + int(
                    rec.get("output_tokens") or 0
                )
            total_tokens += tok
            purpose = str(rec.get("purpose") or "")
            if purpose == "REPLANNING":
                replans += 1
            elif purpose == "REPAIR":
                repairs += 1
            elif purpose == "RETRY" or str(rec.get("kind") or "") == "retry":
                retries += 1
            if rec.get("task_id"):
                tasks.add(str(rec["task_id"]))
            if rec.get("agent_id"):
                agents.add(str(rec["agent_id"]))
            exec_time += float(rec.get("latency") or 0.0)
        return cls(
            total_tokens=int(total_tokens),
            total_cost=round(total_cost, 6),
            llm_calls=int(calls),
            replans=int(replans),
            retries=int(retries),
            repairs=int(repairs),
            task_count=len(tasks),
            execution_time=round(exec_time, 4),
            concurrent_agents=len(agents),
            _budget=budget,
        )


class BudgetEnforcer:
    """预算执行闸 (设计 §3): check 三档 + enforce action 判定。

    check(budget, usage) → {level: ok|warn|review|block, reason, usage, ratio}:
      ratio >= 1.0          → block  (禁止一切 action)
      ratio >= review_ratio → review (停止, 等审批)
      ratio >= warn_ratio   → warn   (继续, 告警)
      其余                  → ok
    enforce(budget, usage, action) → {allowed, level, reason, action}:
      任何 action (llm/execute/retry/repair/replan/new_task) 在 block 级
      allowed=False (设计 §3: 禁止 LLM/retry/repair/replan/new task)。
    """

    LEVEL_OK = "ok"
    LEVEL_WARN = "warn"
    LEVEL_REVIEW = "review"
    LEVEL_BLOCK = "block"

    @classmethod
    def check(cls, budget: Any, usage: Any) -> dict[str, Any]:
        """三档闸门判定 (80%→warn / 90%→review / 100%→block)。"""
        ratio = usage.ratio_with(budget)
        if ratio >= 1.0:
            level = cls.LEVEL_BLOCK
            reason = (
                f"总预算已超限: 消耗比 {ratio:.2%} (>= 100%) — BLOCK, "
                f"禁止 LLM/retry/repair/replan/new task"
            )
        elif ratio >= budget.review_ratio:
            level = cls.LEVEL_REVIEW
            reason = (
                f"预算消耗比 {ratio:.2%} 已达评审线 {budget.review_ratio:.0%} — "
                f"REVIEW, 停止执行等待审批"
            )
        elif ratio >= budget.warn_ratio:
            level = cls.LEVEL_WARN
            reason = (
                f"预算消耗比 {ratio:.2%} 已达告警线 {budget.warn_ratio:.0%} — "
                f"WARN, 继续执行"
            )
        else:
            level = cls.LEVEL_OK
            reason = f"预算消耗比 {ratio:.2%} — 正常 (ok)"
        return {"level": level, "reason": reason, "usage": usage, "ratio": ratio}

    @classmethod
    def enforce(cls, budget: Any, usage: Any, action: str) -> dict[str, Any]:
        """action 级执行判定: block 级任何 action 一律 allowed=False。"""
        result = cls.check(budget, usage)
        level = result["level"]
        allowed = level != cls.LEVEL_BLOCK
        action = str(action or "")
        if allowed:
            reason = f"{result['reason']} | action={action} 允许"
        else:
            reason = (
                f"BUDGET BLOCK: action={action} 被禁止 — {result['reason']}"
            )
        return {
            "allowed": allowed,
            "level": level,
            "reason": reason,
            "action": action,
            "ratio": result["ratio"],
        }
