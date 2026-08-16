"""factory-console/session/debug/debug_engine.py — DebugEngine (S10-068 G6/G8)。

Debug Intelligence 主入口: DebugCase → DebugDecision (完整流程) + feedback 循环
+ 历史/统计 + 持久化 (workspace/debug_cases.json, 失败安全)。

流程 (analyze):
  classify (ErrorAnalyzer) → root_cause (RootCauseAnalyzer) → retrieve
  (DebugExperienceRetriever, Memory Top-K) → strategy (DebugStrategySelector)

Feedback Loop (feedback):
  修复结果 → Memory 沉淀: success → SUCCESS_PATTERN; fail → FAILURE_PATTERN
  (S10-067 ExperienceStore 复用 — 学习闭环: 本次修复成为未来 Debug 经验)

设计: docs/sprint10/S10-068-debug-intelligence-design.md §7
边界:
- 纯标准库; 复用 S10-067 Memory (只读/写入, 不修改); 不替换 Repair Loop
- 失败安全: 持久化异常 → 静默 (不中断调试流); Memory 异常 → 空结果
- LLM 可选 (llm_provider) — 失败 → 规则兜底
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ...memory.experience import (
    DEBUG_EXPERIENCE,  # noqa: F401 — 类型再导出 (兼容导入)
    FAILURE_PATTERN,
    SUCCESS_PATTERN,
    ExperienceRecord,
)
from ...memory.experience_store import DEFAULT_WORKSPACE, ExperienceStore
from . import DebugCase, DebugDecision, FixStrategy
from .debug_memory import DebugExperienceRetriever
from .debug_strategy import DebugStrategySelector
from .error_analysis import ErrorAnalyzer
from .root_cause import RootCauseAnalyzer

#: 调试案件历史文件名 (workspace 级)
DEBUG_CASES_FILE = "debug_cases.json"

#: 成功 outcome 口径 (feedback 判定)
_SUCCESS_OUTCOMES = ("success", "ok", "true", "1", "passed", "pass", "succeeded", "完成", "成功")


def debug_cases_file(workspace: Any = None) -> Path:
    """workspace/debug_cases.json (缺省 → ~/.factory/debug_cases.json)。"""
    root = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
    return root / DEBUG_CASES_FILE


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式。"""
    return datetime.now(timezone.utc).isoformat()


class DebugEngine:
    """调试引擎 (G6): analyze/feedback/history/stats + 持久化。

    analyze(debug_case, *, llm_provider=None, memory_store=None) -> DebugDecision
      完整流程: classify → root_cause → retrieve → strategy → 历史记录。
    feedback(debug_case, decision, outcome, workspace=None) -> None
      修复结果 → Memory 沉淀 (success → SUCCESS_PATTERN; fail → FAILURE_PATTERN)
      + 历史 outcome 更新 (Feedback Loop)。
    history(workspace=None, limit=20) -> list
      debug_cases.json 历史 (最新在前, 失败安全)。
    stats(workspace=None) -> dict
      按 error_type/strategy/outcome 聚合统计。
    """

    def __init__(self, workspace: Any = None) -> None:
        self.workspace = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
        self.analyzer = ErrorAnalyzer()
        self.root_cause_analyzer = RootCauseAnalyzer()
        self.memory_retriever = DebugExperienceRetriever(self.workspace)
        self.strategy_selector = DebugStrategySelector()

    # ------------------------------------------------------------ analyze

    def analyze(
        self,
        debug_case: Any,
        *,
        llm_provider: Any = None,
        memory_store: Any = None,
        workspace: Any = None,
    ) -> DebugDecision:
        """DebugCase → DebugDecision (完整流程; str/dict 输入自动 extract)。

        1) 错误理解 (classify — error_type 空时自动补全)
        2) 根因分析 (root_cause)
        3) 历史经验检索 (retrieve — Memory Top-K)
        4) 策略选择 (strategy)
        5) 历史记录 (workspace/debug_cases.json, 失败安全)
        """
        ws = Path(workspace) if workspace is not None else self.workspace
        case = self._as_case(debug_case)
        if not case.error_type:
            case.error_type = self.analyzer.classify(case.error_message, case.stack_trace)

        root_cause = self.root_cause_analyzer.analyze(
            case, llm_provider=llm_provider
        )
        experiences = self.memory_retriever.retrieve(
            case, memory_store=memory_store
        )
        decision = self.strategy_selector.select(
            root_cause, experiences, case, llm_provider=llm_provider
        )
        self._record(ws, case, decision, outcome="")
        return decision

    # ------------------------------------------------------------ feedback

    def feedback(
        self,
        debug_case: Any,
        decision: Any,
        outcome: str,
        workspace: Any = None,
    ) -> None:
        """修复结果反馈 (G8 — Feedback Loop): 结果 → Memory 沉淀 + 历史更新。

        success (outcome ∈ _SUCCESS_OUTCOMES) → SUCCESS_PATTERN 经验;
        其余 → FAILURE_PATTERN 经验。Memory 写入失败 → 静默 (不中断)。
        """
        ws = Path(workspace) if workspace is not None else self.workspace
        case = self._as_case(debug_case)
        dec = decision if isinstance(decision, DebugDecision) else DebugDecision.from_dict(decision)
        # outcome 兼容: 字符串 ("success"/"fail") 或 dict ({"success": True})
        if isinstance(outcome, dict):
            outcome_val = outcome.get("success", outcome.get("result", outcome.get("status", "")))
            ok = str(outcome_val).strip().lower() in _SUCCESS_OUTCOMES
        else:
            ok = str(outcome or "").strip().lower() in _SUCCESS_OUTCOMES
        outcome_text = str(outcome) if not isinstance(outcome, dict) else (
            "success" if ok else "fail")
        strategy = dec.strategy.value if isinstance(dec.strategy, FixStrategy) else str(dec.strategy)

        record = ExperienceRecord(
            type=SUCCESS_PATTERN if ok else FAILURE_PATTERN,
            project=case.project,
            task=case.task_id or (case.error_message or "")[:40],
            agent=case.agent_id,
            context=(case.error_message or "")[:200],
            problem=case.error_message or case.error_type or "未知错误",
            action=f"{strategy}: {dec.reason}" if dec.reason else strategy,
            result=outcome_text,
            success=ok,
            confidence=max(0.0, min(1.0, dec.confidence)),
            source="debug_feedback",
        )
        try:
            ExperienceStore.from_workspace(ws).add(record)
        except Exception:  # noqa: BLE001 — 失败安全: Memory 写入失败不中断
            pass
        self._update_outcome(ws, case, outcome_text)

    # ------------------------------------------------------------ history / stats

    def history(self, workspace: Any = None, limit: int = 20) -> list[dict[str, Any]]:
        """调试历史 (最新在前, 失败安全: 缺失/损坏 → [])。"""
        ws = Path(workspace) if workspace is not None else self.workspace
        entries = _load_entries(ws)
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return entries[: max(0, int(limit or 0))] if limit else []

    def stats(self, workspace: Any = None) -> dict[str, Any]:
        """调试统计: 总量 + 按错误类型 + 按策略 + 按 outcome。"""
        ws = Path(workspace) if workspace is not None else self.workspace
        entries = _load_entries(ws)
        by_error_type: dict[str, int] = {}
        by_strategy: dict[str, int] = {}
        by_outcome = {"success": 0, "fail": 0, "pending": 0}
        for entry in entries:
            case = entry.get("case") or {}
            decision = entry.get("decision") or {}
            error_type = str(case.get("error_type") or "UNKNOWN")
            by_error_type[error_type] = by_error_type.get(error_type, 0) + 1
            strategy = str(decision.get("strategy") or "UNKNOWN")
            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
            outcome = str(entry.get("outcome") or "").strip().lower()
            if outcome in ("success", "ok", "true", "1", "passed", "pass"):
                by_outcome["success"] += 1
            elif outcome in ("fail", "failure", "failed", "false", "0", "error"):
                by_outcome["fail"] += 1
            else:
                by_outcome["pending"] += 1
        return {
            "total_cases": len(entries),
            "by_error_type": dict(sorted(by_error_type.items())),
            "by_strategy": dict(sorted(by_strategy.items())),
            "by_outcome": by_outcome,
            "file": str(debug_cases_file(ws)),
        }

    # ------------------------------------------------------------ 内部

    def _as_case(self, debug_case: Any) -> DebugCase:
        """输入归一化: DebugCase / dict / str → DebugCase (失败安全)。"""
        if isinstance(debug_case, DebugCase):
            return debug_case
        if isinstance(debug_case, dict):
            return DebugCase.from_dict(debug_case)
        return self.analyzer.extract(str(debug_case or ""))

    def _record(self, ws: Path, case: DebugCase, decision: DebugDecision,
                outcome: str) -> None:
        """历史追加 (workspace/debug_cases.json, 失败安全)。"""
        entry = {
            "id": f"dbg-{uuid.uuid4().hex[:12]}",
            "case": case.to_dict(),
            "decision": decision.to_dict(),
            "outcome": str(outcome or ""),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        try:
            entries = _load_entries(ws)
            entries.append(entry)
            _save_entries(ws, entries)
        except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断调试流
            pass

    def _update_outcome(self, ws: Path, case: DebugCase, outcome: str) -> None:
        """历史 outcome 更新: 匹配最近同 error_message 且未结案的记录。"""
        try:
            entries = _load_entries(ws)
            target = None
            for entry in reversed(entries):
                if entry.get("outcome", "") in ("", "pending") and (entry.get("case") or {}).get(
                    "error_message"
                ) == case.error_message:
                    target = entry
                    break
            if target is None:
                return
            target["outcome"] = str(outcome or "")
            target["updated_at"] = _now_iso()
            _save_entries(ws, entries)
        except Exception:  # noqa: BLE001 — 失败安全
            pass


def _load_entries(ws: Path) -> list[dict[str, Any]]:
    """读 debug_cases.json (缺失/损坏 → [] 失败安全)。"""
    try:
        data = json.loads(debug_cases_file(ws).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 失败安全
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def _save_entries(ws: Path, entries: list[dict[str, Any]]) -> Path:
    """写 debug_cases.json (父目录自动创建; 失败安全)。"""
    path = debug_cases_file(ws)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断
        pass
    return path
