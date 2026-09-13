"""factory-console/session/decision.py — HandoffDecisionEngine (S10-059 P1)。

Autonomous Team Decision (设计 §2 P1): Agent 团队从\"顺序执行\"升级为\"决策驱动\" —
HandoffDecisionEngine 消费 已完成任务 / 依赖 / 冲突 / Agent 角色 → 输出执行决策
(CONTINUE/BLOCK/RETRY/REPAIR/SERIALIZE/SKIP/REQUEST_REVIEW + reason), 落盘
handoff_decisions.json (append, 决策可解释性资产 — GAP G1/G5)。

组件:
- HandoffDecisionEngine — decide(task, *, completed_tasks, next_tasks,
  dependencies, conflicts, workspace, agent_role, records) → 决策 dict
  {decision, reason, conflicting_tasks, strategy, task_id, timestamp};
  record(decision) — append 落盘 handoff_decisions.json (失败安全);
  previous_decisions() / decisions_for(task_id) — 读回 (失败安全 → [])

规则 (优先级从高到低, 设计 §2 P1):
  1. 任务已 completed         → SKIP
  2. 前序任务 failed          → RETRY (retry_count < max_retry) / REPAIR (>= max_retry)
  3. 依赖未满足 (depends_on 未完成) → BLOCK
  4. 同文件冲突 (conflicts 含本任务) → SERIALIZE
  5. requires_review / agent 角色缺失或与 required_role 不匹配 → REQUEST_REVIEW
  6. 默认                     → CONTINUE

设计: docs/sprint10/S10-059-team-decision-design.md §2 (P1)
边界:
- 纯标准库 (json/pathlib/datetime), 零模块依赖; 失败安全 (缺失/损坏 → 空记录, 永不抛)
- 决策引擎只产出决策 + 可解释 reason, 不执行任务、不修改 workspace
  (执行侧决策消费在 orchestrator.TeamRunContext — P4 集成)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 缺省决策资产文件 (~/.factory/teams/handoff_decisions.json — 设计 §4 资产口径;
#: 项目级决策记录 → projects/<slug>/handoff_decisions.json, 由调用方显式指定)
DEFAULT_DECISIONS_FILE = Path.home() / ".factory" / "teams" / "handoff_decisions.json"

#: 项目级决策文件名 (projects/<slug>/handoff_decisions.json — S10-059 资产)
HANDOFF_DECISIONS_FILE_NAME = "handoff_decisions.json"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (决策时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


class HandoffDecisionEngine:
    """自主交接决策引擎 (S10-059 P1): 上下文 → 执行决策 + 可解释 reason。

    decide(): 按优先级规则 (SKIP → RETRY/REPAIR → BLOCK → SERIALIZE →
    REQUEST_REVIEW → CONTINUE) 产出决策; 每次决策可 record 落盘
    handoff_decisions.json (append — 决策历史资产, 可解释性 G5)。
    record()/previous_decisions()/decisions_for() 失败安全 (缺失/损坏 → 空)。
    """

    #: 7 决策常量 (设计 §2 P1)
    DECISION_CONTINUE = "CONTINUE"
    DECISION_BLOCK = "BLOCK"
    DECISION_RETRY = "RETRY"
    DECISION_REPAIR = "REPAIR"
    DECISION_SERIALIZE = "SERIALIZE"
    DECISION_SKIP = "SKIP"
    DECISION_REQUEST_REVIEW = "REQUEST_REVIEW"

    #: 全部合法决策 (缺省回退 CONTINUE — 失败安全)
    DECISIONS: tuple[str, ...] = (
        DECISION_CONTINUE,
        DECISION_BLOCK,
        DECISION_RETRY,
        DECISION_REPAIR,
        DECISION_SERIALIZE,
        DECISION_SKIP,
        DECISION_REQUEST_REVIEW,
    )

    #: 缺省失败判定决策 (前序失败证据 — RETRY/REPAIR 记录即失败信号)
    _FAILURE_DECISIONS: tuple[str, ...] = (DECISION_RETRY, DECISION_REPAIR)

    #: 项目级决策文件名 (projects/<slug>/handoff_decisions.json — S10-059 资产)
    FILE_NAME = HANDOFF_DECISIONS_FILE_NAME

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else DEFAULT_DECISIONS_FILE

    # ------------------------------------------------------------ 决策

    def decide(
        self,
        task: dict[str, Any],
        *,
        completed_tasks: Optional[list[Any]] = None,
        next_tasks: Optional[list[dict[str, Any]]] = None,
        dependencies: Optional[dict[str, list[str]]] = None,
        conflicts: Optional[list[dict[str, Any]]] = None,
        workspace: Optional[dict[str, Any]] = None,
        agent_role: str = "",
        records: Optional[list[dict[str, Any]]] = None,
        max_retry: int = 1,
    ) -> dict[str, Any]:
        """对下一任务产出执行决策 (设计 §2 P1 规则, 优先级从高到低)。

        task: 待决策任务 ({id, name, depends_on?, required_role?, retry_count?,
        status?, requires_review?}); completed_tasks: 已完成任务 (str id 或
        {id, status}); next_tasks: 剩余计划任务 (含 status, 失败证据来源);
        dependencies: {task_id: [depends_on ids]}; conflicts: 冲突记录列表
        ({task_a, task_b, file}); workspace: 工作区上下文 (仅 reason 引用);
        agent_role: 该任务实际 Agent 的角色 (角色匹配校验); records: 历史决策
        (前序失败证据 / 重试历史); max_retry: 重试预算 (缺省 1)。

        返回 {decision, reason, conflicting_tasks, strategy, task_id, timestamp}。
        """
        records = [r for r in (records or []) if isinstance(r, dict)]
        task_id = str(task.get("id") or "")
        conflicts = [c for c in (conflicts or []) if isinstance(c, dict)]
        deps = list(
            dict(dependencies or {}).get(task_id)
            or [str(d) for d in (task.get("depends_on") or []) if not isinstance(d, dict)]
        )
        completed = self._completed_ids(completed_tasks)
        # ---- 规则 1: 任务已 completed → SKIP
        if task_id in completed or str(task.get("status")) == "completed":
            return self._decision(
                self.DECISION_SKIP,
                task_id,
                reason=(
                    f"任务 {task_id} 已完成 (completed_tasks 含 {task_id}), "
                    f"无需重复执行 — SKIP"
                ),
            )
        # ---- 规则 2: 前序任务 failed → RETRY / REPAIR
        failed_dep = self._first_failed_dep(deps, records, next_tasks)
        if failed_dep is not None:
            retry_count = int(task.get("retry_count") or 0)
            budget = int(max_retry) if max_retry is not None else 1
            if retry_count < budget:
                return self._decision(
                    self.DECISION_RETRY,
                    task_id,
                    reason=(
                        f"前序任务 {failed_dep} 执行失败 (retry_count={retry_count} "
                        f"< max_retry={max_retry}); 重试 {task_id} 需先修复/重跑 "
                        f"{failed_dep} — RETRY"
                    ),
                    strategy=f"retry after {failed_dep}",
                )
            return self._decision(
                self.DECISION_REPAIR,
                task_id,
                reason=(
                    f"前序任务 {failed_dep} 执行失败且重试预算耗尽 "
                    f"(retry_count={retry_count} >= max_retry={max_retry}); "
                    f"需人工/RepairManager 修复 — REPAIR"
                ),
                strategy=f"repair {failed_dep}",
            )
        # ---- 规则 3: 依赖未满足 (depends_on 未完成) → BLOCK
        pending_deps = [d for d in deps if d not in completed]
        if pending_deps:
            return self._decision(
                self.DECISION_BLOCK,
                task_id,
                reason=(
                    f"依赖未满足: {', '.join(pending_deps)} 尚未完成 "
                    f"(completed={', '.join(sorted(completed)) or '无'}); "
                    f"阻塞等待前序任务 — BLOCK"
                ),
                strategy="wait for dependencies",
                conflicting_tasks=pending_deps,
            )
        # ---- 规则 4: 同文件冲突 (conflicts 含本任务) → SERIALIZE
        mine = [c for c in conflicts if self._in_conflict(task_id, c)]
        if mine:
            first = mine[0]
            task_a = str(first.get("task_a") or "")
            task_b = str(first.get("task_b") or "")
            file = str(first.get("file") or "")
            others = self._conflicting_tasks(task_id, mine)
            return self._decision(
                self.DECISION_SERIALIZE,
                task_id,
                reason=(
                    f"{task_a} and {task_b} both require write access to "
                    f"{file or 'shared file'} — 串行化: 等待 {task_a} 释放后执行"
                ),
                conflicting_tasks=others,
                strategy=f"execute {task_a} first",
            )
        # ---- 规则 5: requires_review / 角色缺失或不匹配 → REQUEST_REVIEW
        review_reason = self._review_reason(task, agent_role)
        if review_reason:
            return self._decision(
                self.DECISION_REQUEST_REVIEW,
                task_id,
                reason=f"{review_reason} — REQUEST_REVIEW",
                strategy="human review",
            )
        # ---- 规则 6: 默认 → CONTINUE
        return self._decision(
            self.DECISION_CONTINUE,
            task_id,
            reason=(
                f"无冲突、依赖满足、角色匹配 ({agent_role or '未要求角色'}); "
                f"任务 {task_id} 可执行 — CONTINUE"
            ),
        )

    # ------------------------------------------------------------ 记录/读回

    def record(self, decision: dict[str, Any]) -> dict[str, Any]:
        """append 落盘 handoff_decisions.json (失败安全: 读写异常 → 不抛)。"""
        obj = self._normalize_decision(decision)
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
        """读回全部决策记录 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [self._normalize_decision(d) for d in data if isinstance(d, dict)]
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空记录
            pass
        return []

    def decisions_for(self, task_id: str) -> list[dict[str, Any]]:
        """某任务的全部历史决策 (task_id 匹配, 决策时间序)。"""
        key = str(task_id)
        return [d for d in self.previous_decisions() if d.get("task_id") == key]

    def decisions_file(self) -> Path:
        """当前落盘文件路径。"""
        return Path(self._file)

    # ------------------------------------------------------------ 内部

    @classmethod
    def _normalize_decision(cls, decision: Any) -> dict[str, Any]:
        """决策 dict 归一化: 缺失字段失败安全缺省 (decision 未知 → CONTINUE)。"""
        if not isinstance(decision, dict):
            return cls._decision(cls.DECISION_CONTINUE, "", "缺省决策 (空)")
        decision_name = str(decision.get("decision") or cls.DECISION_CONTINUE)
        if decision_name not in cls.DECISIONS:
            decision_name = cls.DECISION_CONTINUE
        return {
            "decision": decision_name,
            "reason": str(decision.get("reason") or ""),
            "conflicting_tasks": [
                str(t)
                for t in (decision.get("conflicting_tasks") or [])
                if not isinstance(t, dict)
            ],
            "strategy": str(decision.get("strategy") or ""),
            "task_id": str(decision.get("task_id") or ""),
            "timestamp": str(decision.get("timestamp") or _now_iso()),
        }

    @classmethod
    def _decision(
        cls,
        decision: str,
        task_id: str,
        *,
        reason: str = "",
        conflicting_tasks: Optional[list[str]] = None,
        strategy: str = "",
    ) -> dict[str, Any]:
        """组装决策 dict (全字段 + timestamp)。"""
        return {
            "decision": decision,
            "reason": reason,
            "conflicting_tasks": list(conflicting_tasks or []),
            "strategy": strategy,
            "task_id": str(task_id),
            "timestamp": _now_iso(),
        }

    @staticmethod
    def _completed_ids(completed_tasks: Optional[list[Any]]) -> set[str]:
        """completed_tasks → id 集合 (str id 或 {id, status} dict 兼容)。"""
        ids: set[str] = set()
        for item in completed_tasks or []:
            if isinstance(item, dict):
                tid = str(item.get("id") or "")
                if tid:
                    ids.add(tid)
            elif item is not None:
                ids.add(str(item))
        return ids

    @classmethod
    def _in_conflict(cls, task_id: str, conflict: dict[str, Any]) -> bool:
        """task_id 是否出现在冲突记录 (task_a/task_b) 中。"""
        if not task_id:
            return False
        return task_id in (str(conflict.get("task_a") or ""), str(conflict.get("task_b") or ""))

    @classmethod
    def _conflicting_tasks(cls, task_id: str, conflicts: list[dict[str, Any]]) -> list[str]:
        """当前任务在全部冲突中的对侧任务 (去重, 不含自身)。"""
        others: list[str] = []
        for c in conflicts:
            for side in ("task_a", "task_b"):
                tid = str(c.get(side) or "")
                if tid and tid != task_id and tid not in others:
                    others.append(tid)
        return others

    @classmethod
    def _first_failed_dep(
        cls,
        deps: list[str],
        records: list[dict[str, Any]],
        next_tasks: Optional[list[dict[str, Any]]],
    ) -> Optional[str]:
        """第一个失败前序 (证据: next_tasks 中 status=failed, 或历史决策
        RETRY/REPAIR 记录); 无失败前序 → None。"""
        failed_by_record = {
            str(r.get("task_id"))
            for r in records
            if str(r.get("decision")) in cls._FAILURE_DECISIONS
        }
        failed_by_status = {
            str(t.get("id"))
            for t in (next_tasks or [])
            if isinstance(t, dict) and str(t.get("status")) == "failed"
        }
        for dep in deps:
            if dep in failed_by_record or dep in failed_by_status:
                return dep
        return None

    @staticmethod
    def _review_reason(task: dict[str, Any], agent_role: str) -> str:
        """REQUEST_REVIEW 触发原因: 显式 requires_review / 角色缺失 / 角色不匹配。
        无 required_role 的任务 → 不做角色校验 (避免误报), 返回 \"\" (不触发)。"""
        if task.get("requires_review"):
            return "任务显式要求人工评审 (requires_review)"
        required_role = str(task.get("required_role") or "").strip()
        if not required_role:
            return ""
        if not str(agent_role or "").strip():
            return f"Agent 角色缺失: 任务要求角色 {required_role}, 但未分配角色"
        if str(agent_role).strip() != required_role:
            return (
                f"Agent 角色不匹配: 任务要求 {required_role}, "
                f"实际角色 {agent_role}"
            )
        return ""
