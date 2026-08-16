"""factory-console/session/loop_guard.py — LoopGuard (S10-063 批次 A)。

Production Governance (GAP G7, 设计 §7): 组合总闸 — 防 retry/repair/replan/
task proposal 乘法爆炸 + 反复失败/反复决策/总执行上限。

限制 (__init__ 可配置):
- max_retry / max_repair / max_replan / max_generated_tasks — 各动作上限
- max_same_failure — 同 task 同 failure 反复 (>= 阈值 → review; >= 2×阈值 → block)
- max_same_decision — 同一决策反复 (>= 阈值 → review)
- max_total_execution — 总执行次数 (组合总闸, >= 阈值 → block)

接口:
- check_failure(task_id, failure_key, history) → {allowed, action, reason}:
  action ∈ retry|repair|replan|review|block; 升级阶梯 retry → repair →
  replan → review/block; 失败安全 (空 history → allowed retry)
- check_decision(decision, decision_history) → {allowed, reason}:
  同决策反复 → review; 生成任务数 → block; 总执行 → block
- same_failure_count / same_decision_count / total_execution_count —
  计数辅助 (失败安全: 非列表 → 0)

history 记录约定 (dict): {task_id, failure|failure_key, action: "retry"|
"repair"|"replan"|..., decision, kind: "new_task"|...}; 宽松兼容 (缺字段忽略)。

设计: docs/sprint10/S10-063-production-governance-design.md §7
边界: 纯标准库, 零依赖, 不修改任何现有模块; 只判定, 不执行动作。
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------- action 常量

ACTION_RETRY = "retry"
ACTION_REPAIR = "repair"
ACTION_REPLAN = "replan"
ACTION_REVIEW = "review"
ACTION_BLOCK = "block"


class LoopGuard:
    """组合总闸 (设计 §7): 同失败/同决策/总执行 + retry→repair→replan 阶梯。

    __init__ 缺省: max_retry=1 / max_repair=2 / max_replan=5 /
    max_generated_tasks=10 / max_same_failure=3 / max_same_decision=5 /
    max_total_execution=50 (与 ProjectBudget 缺省对齐)。
    """

    ACTION_RETRY = ACTION_RETRY
    ACTION_REPAIR = ACTION_REPAIR
    ACTION_REPLAN = ACTION_REPLAN
    ACTION_REVIEW = ACTION_REVIEW
    ACTION_BLOCK = ACTION_BLOCK

    def __init__(
        self,
        max_retry: int = 1,
        max_repair: int = 2,
        max_replan: int = 5,
        max_generated_tasks: int = 10,
        max_same_failure: int = 3,
        max_same_decision: int = 5,
        max_total_execution: int = 50,
    ) -> None:
        self.max_retry = int(max_retry)
        self.max_repair = int(max_repair)
        self.max_replan = int(max_replan)
        self.max_generated_tasks = int(max_generated_tasks)
        self.max_same_failure = int(max_same_failure)
        self.max_same_decision = int(max_same_decision)
        self.max_total_execution = int(max_total_execution)

    # ------------------------------------------------------------ check_failure

    def check_failure(
        self, task_id: str, failure_key: str, history: Any
    ) -> dict[str, Any]:
        """任务失败处理判定 → {allowed, action, reason} (失败安全)。

        优先级 (从高到低):
        1. 总执行次数 >= max_total_execution         → block (组合总闸)
        2. 同 task 同 failure >= 2×max_same_failure → block (死循环)
        3. 同 task 同 failure >= max_same_failure   → review (需人工)
        4. 项目 replan 次数 >= max_replan           → review (重规划超限)
        5. 该 task repair 次数 >= max_repair        → replan (建议升级)
        6. 该 task retry 次数 >= max_retry          → repair (建议升级)
        7. 其余                                     → retry (allowed)

        allowed=False 仅出现在 block/review (必须停止/等人工);
        repair/replan 建议动作 allowed=True (调用方按建议升级)。
        """
        history = history if isinstance(history, list) else []
        tid = str(task_id or "")
        key = str(failure_key or "")

        total = self.total_execution_count(history)
        if total >= self.max_total_execution:
            return {
                "allowed": False,
                "action": ACTION_BLOCK,
                "reason": (
                    f"总执行次数 {total} >= max_total_execution "
                    f"{self.max_total_execution} — 组合总闸 BLOCK"
                ),
            }

        same = self.same_failure_count(tid, key, history)
        if same >= self.max_same_failure * 2:
            return {
                "allowed": False,
                "action": ACTION_BLOCK,
                "reason": (
                    f"任务 {tid} 同失败 '{key}' 重复 {same} 次 "
                    f"(>= {self.max_same_failure * 2}) — BLOCK"
                ),
            }
        if same >= self.max_same_failure:
            return {
                "allowed": False,
                "action": ACTION_REVIEW,
                "reason": (
                    f"任务 {tid} 同失败 '{key}' 重复 {same} 次 "
                    f"(>= {self.max_same_failure}) — 需人工评审"
                ),
            }

        replans = self._count_action(history, ACTION_REPLAN)
        if replans >= self.max_replan:
            return {
                "allowed": False,
                "action": ACTION_REVIEW,
                "reason": (
                    f"重规划 {replans} 次 >= max_replan {self.max_replan} — "
                    f"需人工评审"
                ),
            }

        repairs = self._count_for_task(history, tid, (ACTION_REPAIR,))
        if repairs >= self.max_repair:
            return {
                "allowed": True,
                "action": ACTION_REPLAN,
                "reason": (
                    f"任务 {tid} repair {repairs} 次 >= max_repair "
                    f"{self.max_repair} — 建议 replan"
                ),
            }

        retries = self._count_for_task(history, tid, (ACTION_RETRY,))
        if retries >= self.max_retry:
            return {
                "allowed": True,
                "action": ACTION_REPAIR,
                "reason": (
                    f"任务 {tid} retry {retries} 次 >= max_retry "
                    f"{self.max_retry} — 建议 repair"
                ),
            }

        return {
            "allowed": True,
            "action": ACTION_RETRY,
            "reason": (
                f"任务 {tid} retry {retries}/{self.max_retry} — 允许 retry"
            ),
        }

    # ------------------------------------------------------------ check_decision

    def check_decision(self, decision: str, decision_history: Any) -> dict[str, Any]:
        """决策判定 → {allowed, reason} (失败安全): 同决策反复 → review;
        生成任务超限 → block; 总执行超限 → block; 其余 → allowed。"""
        history = decision_history if isinstance(decision_history, list) else []
        d = str(decision or "")

        total = self.total_execution_count(history)
        if total >= self.max_total_execution:
            return {
                "allowed": False,
                "reason": (
                    f"总执行次数 {total} >= max_total_execution "
                    f"{self.max_total_execution} — BLOCK"
                ),
            }

        generated = self._count_kind(history, "new_task") + self._count_action(
            history, "create_task"
        )
        if generated >= self.max_generated_tasks:
            return {
                "allowed": False,
                "reason": (
                    f"生成任务 {generated} 个 >= max_generated_tasks "
                    f"{self.max_generated_tasks} — BLOCK"
                ),
            }

        same = self.same_decision_count(d, history)
        if same >= self.max_same_decision:
            return {
                "allowed": False,
                "reason": (
                    f"同一决策 '{d}' 重复 {same} 次 "
                    f"(>= {self.max_same_decision}) — 需人工评审"
                ),
            }

        return {"allowed": True, "reason": f"决策 '{d}' 未见异常重复"}

    # ------------------------------------------------------------ 计数

    def same_failure_count(
        self, task_id: str, failure_key: str, history: Any
    ) -> int:
        """同 task 同 failure 出现次数 (失败安全: 非列表/缺字段 → 0)。"""
        if not isinstance(history, list):
            return 0
        tid = str(task_id or "")
        key = str(failure_key or "")
        count = 0
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("task_id") or "") != tid:
                continue
            failure = str(
                entry.get("failure") or entry.get("failure_key") or ""
            )
            if failure == key:
                count += 1
        return count

    def same_decision_count(self, decision: str, history: Any) -> int:
        """同一决策出现次数 (dict 的 decision 键 或 裸字符串条目, 失败安全)。"""
        if not isinstance(history, list):
            return 0
        d = str(decision or "")
        count = 0
        for entry in history:
            if isinstance(entry, dict):
                if str(entry.get("decision") or "") == d:
                    count += 1
            elif str(entry) == d:
                count += 1
        return count

    def total_execution_count(self, history: Any) -> int:
        """总执行次数 (组合总闸): 每条带 task_id 的 dict 记录 或 非 dict 条目
        计一次执行尝试 (失败安全: 非列表 → 0)。"""
        if not isinstance(history, list):
            return 0
        count = 0
        for entry in history:
            if isinstance(entry, dict):
                if entry.get("task_id") is not None:
                    count += 1
            else:
                count += 1
        return count

    # ------------------------------------------------------------ 内部

    def _count_for_task(
        self, history: list, task_id: str, actions: tuple[str, ...]
    ) -> int:
        """某 task 某类 action 的历史次数 (宽松: action/kind 任一命中)。"""
        count = 0
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("task_id") or "") != task_id:
                continue
            if str(entry.get("action") or "") in actions or str(
                entry.get("kind") or ""
            ) in actions:
                count += 1
        return count

    def _count_action(self, history: list, action: str) -> int:
        """全局某类 action 次数 (计划级 — 不按 task 过滤)。"""
        count = 0
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("action") or "") == action or str(
                entry.get("kind") or ""
            ) == action:
                count += 1
        return count

    def _count_kind(self, history: list, kind: str) -> int:
        """某 kind 标记次数 (生成任务等)。"""
        count = 0
        for entry in history:
            if isinstance(entry, dict) and str(entry.get("kind") or "") == kind:
                count += 1
        return count
