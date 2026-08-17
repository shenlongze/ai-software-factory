"""factory-console/session/debug/strategy_adaptation.py — StrategyAdapter (S10-068 Part 2, G2)。

Strategy Adaptation: strategy_history 排除已失败策略; Memory 替代经验 → 新策略;
全部策略失败 → REQUEST_REVIEW (不无限重复同一策略)。

设计: docs/sprint10/S10-068-part2-design.md §3
边界:
- 纯标准库, 零模块依赖; 复用 FixStrategy/coerce_strategy (校验铁律)
- evaluate 失败安全: 任意输入 → bool (dict/ValidationResult/对象/裸值)
- next_strategy 不抛 (空可用集 → REQUEST_REVIEW 兜底)
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from . import FixStrategy, coerce_strategy

#: 缺省策略候选顺序 (可用策略面 — 不含 REQUEST_REVIEW, 由全败兜底产生)
DEFAULT_AVAILABLE: tuple[str, ...] = (
    FixStrategy.FIX_CODE.value,
    FixStrategy.FIX_TEST.value,
    FixStrategy.CHANGE_DESIGN.value,
    FixStrategy.ROLLBACK.value,
)

#: 经验 action 前缀 → 策略映射 (Memory 替代经验 → 新策略)
_ACTION_PREFIXES: dict[str, str] = {
    "FIX_CODE": FixStrategy.FIX_CODE.value,
    "FIX_TEST": FixStrategy.FIX_TEST.value,
    "CHANGE_DESIGN": FixStrategy.CHANGE_DESIGN.value,
    "ROLLBACK": FixStrategy.ROLLBACK.value,
}


def _as_bool(value: Any) -> bool:
    """任意尝试结果 → bool (失败安全: 未知 → False)。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if "success" in value:
            return bool(value["success"])
        validation = value.get("validation")
        if isinstance(validation, dict):
            return bool(validation.get("success"))
        if isinstance(validation, bool):
            return validation
        if "passed" in value:
            return bool(value["passed"])
        return bool(value.get("ok", False))
    if hasattr(value, "success"):
        return bool(value.success)
    text = str(value or "").strip().lower()
    return text in ("success", "pass", "passed", "true", "1", "ok", "succeeded", "完成", "成功")


class StrategyAdapter:
    """策略适配器 (G2): evaluate / next_strategy / history / failed_strategies。

    evaluate(attempt_result) -> bool — 当前策略是否成功 (宽松口径);
    next_strategy(session, available) -> FixStrategy — 排除已失败策略,
      取第一个未尝试候选; Memory 成功经验 action 前缀可注入候选;
      全部失败 → REQUEST_REVIEW (全败→人工评审);
    history(session) -> list[dict] — strategy_history 记录视图;
    failed_strategies(session) -> set[str] — 已失败策略集合。
    """

    def evaluate(self, attempt_result: Any) -> bool:
        """当前策略是否成功 (dict/ValidationResult/对象/裸值, 失败安全)。"""
        return _as_bool(attempt_result)

    def failed_strategies(self, session: Any) -> set[str]:
        """已失败策略集合 (strategy_history 中 status=failed 或验证失败)。"""
        failed: set[str] = set()
        for attempt in self._attempts(session):
            if self._attempt_failed(attempt):
                strategy = str(getattr(attempt, "strategy", None) or "")
                if strategy:
                    failed.add(strategy)
        return failed

    def next_strategy(
        self,
        session: Any,
        available: Optional[Iterable[Any]] = None,
    ) -> FixStrategy:
        """下一个策略: 排除已失败 → 取首个候选; 空 → REQUEST_REVIEW。"""
        pool = [s for s in (available or DEFAULT_AVAILABLE)]
        candidates: list[FixStrategy] = []
        for value in pool:
            try:
                strategy = coerce_strategy(value)
            except ValueError:
                continue
            if strategy == FixStrategy.REQUEST_REVIEW:
                continue
            if strategy.value not in self.failed_strategies(session):
                candidates.append(strategy)
        if not candidates:
            return FixStrategy.REQUEST_REVIEW
        return candidates[0]

    def memory_alternatives(self, session: Any) -> list[str]:
        """Memory 替代经验 → 新策略候选 (成功经验 action 前缀映射)。

        返回未尝试过的策略值列表 (action 前缀如 "FIX_CODE: ..." → FIX_CODE)。
        """
        alternatives: list[str] = []
        failed = self.failed_strategies(session)
        for exp in self._experiences(session):
            if not _record_success(exp):
                continue
            action = str(getattr(exp, "action", None) or "")
            if not action and isinstance(exp, dict):
                action = str(exp.get("action") or "")
            prefix = action.split(":", 1)[0].strip().upper()
            strategy = _ACTION_PREFIXES.get(prefix)
            if strategy and strategy not in failed and strategy not in alternatives:
                alternatives.append(strategy)
        return alternatives

    def history(self, session: Any) -> list[dict[str, Any]]:
        """strategy_history 记录视图 (list[DebugAttempt.to_dict()])。"""
        return [
            a.to_dict() if hasattr(a, "to_dict") else a
            for a in self._attempts(session)
        ]

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _attempts(session: Any) -> list[Any]:
        """会话尝试记录 (宽松: 对象属性 / dict 键)。"""
        if session is None:
            return []
        history = getattr(session, "strategy_history", None)
        if history is None and isinstance(session, dict):
            history = session.get("strategy_history")
        return list(history or [])

    @staticmethod
    def _experiences(session: Any) -> list[Any]:
        """会话检索经验 (宽松: 对象属性 / dict 键)。"""
        if session is None:
            return []
        experiences = getattr(session, "retrieved_experiences", None)
        if experiences is None and isinstance(session, dict):
            experiences = session.get("retrieved_experiences")
        return list(experiences or [])

    def _attempt_failed(self, attempt: Any) -> bool:
        """单次尝试是否失败 (status=failed 或 validation_result success=False)。"""
        status = str(getattr(attempt, "status", None) or "")
        if status == "failed":
            return True
        validation = getattr(attempt, "validation_result", None)
        if validation is not None:
            return not _as_bool(validation)
        return False


def _record_success(record: Any) -> bool:
    """经验记录是否成功 (对象/字典, 失败安全 → False)。"""
    if isinstance(record, dict):
        return bool(record.get("success", False))
    return bool(getattr(record, "success", False))
