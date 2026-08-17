"""factory-console/session/debug/debug_pipeline.py — DebugPipeline (S10-068 Part 2, G1/G3/G5/G10)。

完整闭环: start → analyze (classify→root_cause→retrieve→strategy) →
repair (RepairSafety 治理闸 → 执行) → validate (PASS→SUCCESS / FAIL→RETRYING)
→ adapt (strategy_history + 替代策略) → ... 循环 → SUCCESS / BLOCKED /
WAITING_FOR_REVIEW → resume (REVIEW 通过后继续) → learn (Memory 沉淀 + DebugTrace)。

设计: docs/sprint10/S10-068-part2-design.md §8
复用 (只读, 不修改): Part 1 DebugEngine/ErrorAnalyzer/RootCauseAnalyzer/
DebugExperienceRetriever/DebugStrategySelector; S10-063 LoopGuard/BudgetEnforcer/
ExecutionPolicy/ReviewGate; S10-067 ExperienceStore; quality.py RepairManager
(薄调点 — execute_fn 注入)。

边界:
- 纯标准库, 零新依赖; 失败安全: LLM/执行/落盘异常 → 规则兜底, 绝不裸抛
- 缺省 execute_fn = 确定性策略应用桩 (无真实执行引擎 — 真实系统注入
  RepairManager/Agent Runtime 桥); 不绕过 Governance (RepairSafety 强制)
- CLI→Core→API 同一入口 (actions/api 都调 DebugPipeline)
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from ...memory.experience import (
    FAILURE_PATTERN,
    SUCCESS_PATTERN,
    ExperienceRecord,
)
from ...memory.experience_store import DEFAULT_WORKSPACE, ExperienceStore
from ..quality import RepairManager
from . import (
    DebugCase,
    FixStrategy,
    SESSION_ANALYZING,
    SESSION_BLOCKED,
    SESSION_REPAIRING,
    SESSION_RETRYING,
    SESSION_STRATEGY_SELECTED,
    SESSION_SUCCESS,
    SESSION_VALIDATING,
    SESSION_WAITING_FOR_REVIEW,
)
from .debug_session import (
    DebugAttempt,
    DebugSession,
    DebugSessionStore,
    _now_iso,
)
from .debug_trace import DebugTrace
from .repair_safety import (
    DECISION_AUTO,
    DECISION_BLOCKED,
    DECISION_REVIEW,
    DECISION_SAFE_AUTO,
    RepairSafety,
)
from .retrieval_policy import DebugRetrievalPolicy
from .strategy_adaptation import DEFAULT_AVAILABLE, StrategyAdapter

#: 修复执行函数契约: (session: DebugSession, workspace: Path) -> dict
#: dict 至少含 {"success": bool}; 可选 {"validation", "cost", "latency", ...}
RepairExecuteFn = Callable[[Any, Path], dict[str, Any]]

#: 验证函数契约: (session, outcome: dict) -> ValidationResult/dict/bool
ValidateFn = Callable[[Any, dict[str, Any]], Any]


def _default_execute_fn() -> RepairExecuteFn:
    """缺省修复执行器: 确定性策略应用桩 (无真实执行引擎)。

    真实系统: 调用方注入 execute_fn (薄调 RepairManager.repair / Agent Runtime
    桥) — 本桩保证 Pipeline 在无执行环境时仍可演示完整闭环与治理决策。
    """

    def execute(session: Any, workspace: Path) -> dict[str, Any]:
        strategy = str(getattr(session, "selected_strategy", "") or "")
        return {
            "success": True,
            "strategy": strategy,
            "note": "deterministic repair applied (no execution engine)",
            "validation_command": getattr(session, "validation_command", "") or "",
        }

    return execute


def _production_default_execute_fn() -> RepairExecuteFn:
    """S10-071 P0-1: 生产默认修复执行器 — 真实 Workspace 修改 (非桩)。

    替代 _default_execute_fn 作为默认: 真实修改文件 (snapshot/diff/rollback)。
    旧桩保留为显式测试 seam (注入时使用)。
    """
    from .workspace_executor import production_execute_fn

    return production_execute_fn()


def _production_default_validator_fn():
    """S10-071 P0-2: 生产默认验证器 — 真实 pytest (非注入)。

    替代注入 validator: subprocess 执行真实 pytest。
    """

    def validate(session: Any, outcome: Any = None, *, workspace: Any = None) -> dict:
        from .workspace_executor import PytestValidator

        v = PytestValidator().validate(workspace)
        return {"success": v.success, "exit_code": v.exit_code,
                "summary": v.summary, "error": v.error, "duration": v.duration}

    return validate


def repair_manager_execute_fn(
    repair_manager: Optional[RepairManager] = None,
    task_execute_fn: Any = None,
    validator: Any = None,
) -> RepairExecuteFn:
    """RepairManager 薄调桥 (S10-053 复用): 会话 → RepairManager 修复执行。

    以 workspace 为 project_dir 建 repair_task.json 记录并执行一次 repair,
    结果映射为 Pipeline 执行输出 ({"success", "validation", "repair_id"})。
    失败安全: RepairManager 异常 → {"success": False, "error": str(exc)}。
    """

    def execute(session: Any, workspace: Path) -> dict[str, Any]:
        manager = repair_manager if repair_manager is not None else RepairManager()
        project_dir = Path(workspace)
        try:
            original_task: dict[str, Any] = {
                "id": str(getattr(session, "task_id", "") or "")
                or str(getattr(session, "debug_id", "") or ""),
                "name": str(getattr(session, "error_summary", "") or "")[:60],
            }
            repair = RepairManager.create_repair(
                project_dir,
                original_task,
                str(getattr(session, "error_summary", "") or "未知失败"),
                retry_count=int(getattr(session, "attempt_number", 0) or 0),
            )
            result = manager.repair(
                project_dir,
                execute_fn=task_execute_fn,
                validator=validator,
            )
            status = str(result.get("status") or "")
            return {
                "success": status == "completed",
                "validation": result.get("validation"),
                "repair_id": result.get("repair_id"),
                "repair_status": status,
                "retry_count": int(result.get("retry_count") or 0),
                "repair_record": repair,
            }
        except Exception as exc:  # noqa: BLE001 — 失败安全: 修复异常 → 失败结果
            return {"success": False, "error": str(exc)}

    return execute


class DebugPipeline:
    """自主调试与修复管线 (G10): start/analyze/repair/validate/adapt/run/
    resume/learn — CLI→Core→API 同一入口。"""

    def __init__(
        self,
        workspace: Any = None,
        *,
        store: Optional[DebugSessionStore] = None,
        trace: Optional[DebugTrace] = None,
        safety: Optional[RepairSafety] = None,
        adapter: Optional[StrategyAdapter] = None,
        retrieval: Optional[DebugRetrievalPolicy] = None,
        engine: Any = None,
    ) -> None:
        self.workspace = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
        self.store = store if store is not None else DebugSessionStore(self.workspace)
        self.trace = trace if trace is not None else DebugTrace(self.workspace)
        self.safety = safety if safety is not None else RepairSafety()
        self.adapter = adapter if adapter is not None else StrategyAdapter()
        self.retrieval = retrieval if retrieval is not None else DebugRetrievalPolicy(self.workspace)
        # DebugEngine 惰性装配 (避免顶层循环依赖)
        self._engine = engine

    # ------------------------------------------------------------ 装配

    @property
    def engine(self) -> Any:
        """DebugEngine 实例 (惰性 — 复用 Part 1 分析引擎)。"""
        if self._engine is None:
            from .debug_engine import DebugEngine

            self._engine = DebugEngine(self.workspace)
        return self._engine

    # ------------------------------------------------------------ start

    def start(
        self,
        project_id: str = "",
        task_id: str = "",
        agent_id: str = "",
        error_message: str = "",
        *,
        failure_id: str = "",
        context: str = "",
        previous_attempts: int = 0,
    ) -> DebugSession:
        """开始调试会话 (ANALYZING; 落盘; 返回会话)。"""
        message = str(error_message or "").strip()
        now = _now_iso()
        session = DebugSession(
            debug_id=f"dbg-{uuid.uuid4().hex[:12]}",
            error_summary=message or "未知错误",
            project_id=str(project_id or ""),
            task_id=str(task_id or ""),
            agent_id=str(agent_id or ""),
            failure_id=str(failure_id or ""),
            status=SESSION_ANALYZING,
            timestamps={"created_at": now, "updated_at": now},
            trace_id=f"trc-{uuid.uuid4().hex[:12]}",
        )
        # context 透传: 若无 task/project 信息, 用 context 兜底查询面
        if not session.task_id and context:
            session.error_summary = f"{session.error_summary} ({context})" if message else str(context)
        self.store.create(session)
        return session

    # ------------------------------------------------------------ analyze

    def analyze(
        self,
        session: Any,
        *,
        llm_provider: Any = None,
        memory_store: Any = None,
        top_k: int = 3,
    ) -> DebugSession:
        """分析: classify → root_cause → retrieve → strategy (STRATEGY_SELECTED)。"""
        session = self._as_session(session)
        try:
            case = DebugCase(
                error_message=session.error_summary,
                error_type=session.error_type,
                stack_trace="",
                task_id=session.task_id,
                agent_id=session.agent_id,
                context=session.error_summary,
                previous_attempts=session.attempt_number,
                project=session.project_id,
            )
            if not case.error_type:
                case.error_type = self.engine.analyzer.classify(
                    case.error_message, case.stack_trace
                )
            session.error_type = case.error_type
            root = self.engine.root_cause_analyzer.analyze(
                case, llm_provider=llm_provider
            )
            session.root_cause = root.to_dict()
            session.root_cause_confidence = root.confidence
            session.evidence = list(root.evidence)

            # 检索策略 (DebugRetrievalPolicy 统一入口 — Top-K + 排序 + 去重)
            experiences = self.retrieval.retrieve(
                session, memory_store=memory_store, top_k=top_k
            )
            session.retrieved_experiences = [
                r.to_dict() if hasattr(r, "to_dict") else r for r in experiences
            ]
            decision = self.engine.strategy_selector.select(
                root, experiences, case, llm_provider=llm_provider
            )
            session.selected_strategy = decision.strategy.value
            session.transition(SESSION_STRATEGY_SELECTED)
        except Exception as exc:  # noqa: BLE001 — 失败安全: 分析异常 → 停
            session.budget_usage = {
                "decision": DECISION_BLOCKED,
                "reason": f"分析失败: {exc}",
                "phase": "analyze",
            }
            session.transition(SESSION_BLOCKED)
        self.store.update(session)
        return session

    # ------------------------------------------------------------ repair

    def repair(
        self,
        session: Any,
        *,
        workspace: Any = None,
        budget: Any = None,
        usage: Any = None,
        loop_guard: Any = None,
        history: Any = None,
        policy: Any = None,
        review_gate: Any = None,
        execute_fn: Optional[RepairExecuteFn] = None,
        validator: Optional[ValidateFn] = None,
        validation_command: str = "",
        max_attempts: int = 3,
    ) -> DebugSession:
        """修复: RepairSafety.check → AUTO/SAFE_AUTO: 执行; REVIEW: 请求审批;
        BLOCKED: 停 (不绕过 Governance)。"""
        session = self._as_session(session)
        ws = Path(workspace) if workspace is not None else self.workspace
        decision, reason = self.safety.check(
            session,
            budget=budget,
            usage=usage,
            loop_guard=loop_guard,
            history=history,
            policy=policy,
            review_gate=review_gate,
            max_attempts=max_attempts,
        )
        session.budget_usage = {
            "decision": decision,
            "reason": reason,
            "attempt": session.attempt_number,
            "phase": "repair",
        }
        if decision == DECISION_BLOCKED:
            session.transition(SESSION_BLOCKED)
            self.store.update(session)
            return session
        if decision == DECISION_REVIEW:
            session.transition(SESSION_WAITING_FOR_REVIEW)
            self.store.update(session)
            return session

        # AUTO / SAFE_AUTO — 执行修复
        session.transition(SESSION_REPAIRING)
        if validation_command:
            session.validation_command = validation_command
        outcome = self._execute(
            session, ws, execute_fn=execute_fn, validator=validator
        )
        ok = bool(outcome.get("success"))
        attempt = DebugAttempt(
            attempt_number=session.attempt_number + 1,
            strategy=session.selected_strategy,
            strategy_reason=str(
                (session.budget_usage or {}).get("reason") or "策略选择"
            ),
            validation_command=session.validation_command,
            validation_result=session.validation_result,
            status="passed" if ok else "failed",
            timestamps={
                "started_at": _now_iso(),
                "finished_at": _now_iso(),
            },
            cost=float(outcome.get("cost") or 0.0),
        )
        session.strategy_history.append(attempt)
        session.attempt_number += 1
        session.transition(SESSION_VALIDATING)
        self.store.update(session)
        return session

    # ------------------------------------------------------------ validate

    def validate(
        self,
        session: Any,
        *,
        validation_command: str = "",
        result: Any = None,
    ) -> DebugSession:
        """验证: PASS → SUCCESS; FAIL → RETRYING (不无限重试由 run/repair 把关)。"""
        session = self._as_session(session)
        if session.status not in (SESSION_VALIDATING, SESSION_REPAIRING, SESSION_RETRYING):
            session.transition(SESSION_VALIDATING)
        if validation_command:
            session.validation_command = validation_command
        if result is not None:
            ok = self.adapter.evaluate(result)
            session.validation_result = (
                result if isinstance(result, (dict, bool)) else {"success": ok}
            )
        else:
            ok = self.adapter.evaluate(session.validation_result)
        if ok:
            session.transition(SESSION_SUCCESS)
        else:
            session.transition(SESSION_RETRYING)
        self.store.update(session)
        return session

    # ------------------------------------------------------------ adapt

    def adapt(
        self,
        session: Any,
        *,
        available: Any = None,
        memory_store: Any = None,
    ) -> DebugSession:
        """策略适配: 排除已失败策略 + Memory 替代经验 → 新策略; 全败 → REVIEW。"""
        session = self._as_session(session)
        pool = list(available) if available is not None else self._default_available(session)
        strategy = self.adapter.next_strategy(session, pool)
        session.selected_strategy = strategy.value
        if strategy == FixStrategy.REQUEST_REVIEW:
            session.budget_usage = {
                "decision": DECISION_REVIEW,
                "reason": "全部策略已失败 — 请求人工评审",
                "phase": "adapt",
            }
            session.transition(SESSION_WAITING_FOR_REVIEW)
        else:
            session.transition(SESSION_STRATEGY_SELECTED)
        self.store.update(session)
        return session

    # ------------------------------------------------------------ run

    def run(
        self,
        session: Any,
        *,
        workspace: Any = None,
        max_attempts: int = 3,
        budget: Any = None,
        usage: Any = None,
        loop_guard: Any = None,
        history: Any = None,
        policy: Any = None,
        review_gate: Any = None,
        execute_fn: Optional[RepairExecuteFn] = None,
        validator: Optional[ValidateFn] = None,
        llm_provider: Any = None,
        memory_store: Any = None,
    ) -> DebugSession:
        """完整闭环: analyze→repair→validate→adapt 循环 (不无限重试)。"""
        session = self._as_session(session)
        if session.status == SESSION_ANALYZING:
            self.analyze(session, llm_provider=llm_provider, memory_store=memory_store)
        if session.status == SESSION_WAITING_FOR_REVIEW:
            return session  # 等待人工 — 不自动继续

        guard = 0
        ceiling = max(2, int(max_attempts or 3)) * 4
        while (
            session.status not in (SESSION_SUCCESS, SESSION_BLOCKED, SESSION_WAITING_FOR_REVIEW)
            and session.attempt_number < max_attempts
            and guard < ceiling
        ):
            guard += 1
            self.repair(
                session,
                workspace=workspace,
                budget=budget,
                usage=usage,
                loop_guard=loop_guard,
                history=history,
                policy=policy,
                review_gate=review_gate,
                execute_fn=execute_fn,
                validator=validator,
                max_attempts=max_attempts,
            )
            if session.status in (SESSION_BLOCKED, SESSION_WAITING_FOR_REVIEW):
                break
            self.validate(session)
            if session.status == SESSION_SUCCESS:
                break
            if session.status == SESSION_RETRYING:
                self.adapt(session, memory_store=memory_store)
        # 兜底: 循环耗尽仍 RETRYING → 全败评审 (不无限重试铁律)
        if session.status == SESSION_RETRYING and session.attempt_number >= max_attempts:
            session.transition(SESSION_WAITING_FOR_REVIEW)
            session.budget_usage = {
                "decision": "REVIEW",
                "reason": f"已达 max_attempts {max_attempts} 仍失败 — 请求人工评审",
                "phase": "run",
            }
            self.store.update(session)
        return session

    # ------------------------------------------------------------ resume

    def resume(
        self,
        session: Any,
        *,
        decision: str = "approved",
        workspace: Any = None,
    ) -> DebugSession:
        """继续调试 (REVIEW 通过后): approved → 重新 REPAIRING (再次 repair 即
        继续执行); rejected → BLOCKED。非等待态 → 原样返回 (幂等, 失败安全)。"""
        session = self._as_session(session)
        if session.status != SESSION_WAITING_FOR_REVIEW:
            return session
        verdict = str(decision or "").strip().lower()
        if verdict in ("approved", "approve", "ok", "yes", "true", "1", "同意", "通过", "继续"):
            session.transition(SESSION_REPAIRING)
        else:
            session.transition(SESSION_BLOCKED)
        self.store.update(session)
        return session

    # ------------------------------------------------------------ learn

    def learn(
        self,
        session: Any,
        *,
        workspace: Any = None,
        cost: Any = None,
        tokens: Any = None,
        latency: Any = None,
        memory_store: Any = None,
    ) -> None:
        """学习: 成功/失败 → Memory 沉淀 (SUCCESS_PATTERN/FAILURE_PATTERN) +
        DebugTrace (Audit-ready)。失败安全: Memory/Trace 异常 → 静默。"""
        session = self._as_session(session)
        ws = Path(workspace) if workspace is not None else self.workspace
        ok = session.status == SESSION_SUCCESS
        try:
            store = (
                memory_store
                if memory_store is not None
                else ExperienceStore.from_workspace(ws)
            )
            strategy = session.selected_strategy or "UNKNOWN"
            record = ExperienceRecord(
                type=SUCCESS_PATTERN if ok else FAILURE_PATTERN,
                project=session.project_id,
                task=session.task_id or (session.error_summary or "")[:40],
                agent=session.agent_id,
                context=(session.error_summary or "")[:200],
                problem=session.error_summary or session.error_type or "未知错误",
                action=strategy,
                result="success" if ok else "failed",
                success=ok,
                confidence=session.root_cause_confidence,
                source="debug_pipeline",
            )
            store.add(record)
        except Exception:  # noqa: BLE001 — 失败安全: Memory 写入失败不中断
            pass
        total_cost = float(cost) if cost is not None else sum(
            float(getattr(a, "cost", 0.0) or 0.0) for a in session.strategy_history
        )
        self.trace.record(
            session,
            governance=session.budget_usage,
            cost=total_cost,
            tokens=tokens,
            latency=latency,
        )

    # ------------------------------------------------------------ 内部

    def _as_session(self, session: Any) -> DebugSession:
        """输入归一化: DebugSession / dict → DebugSession (dict → from_dict)。"""
        if isinstance(session, DebugSession):
            return session
        if isinstance(session, dict):
            return DebugSession.from_dict(session)
        raise ValueError(f"DebugPipeline 需要 DebugSession/dict, 收到 {type(session).__name__}")

    def _default_available(self, session: Any) -> list[str]:
        """默认候选: 标准策略面 + Memory 替代经验 (成功经验 action 前缀)。"""
        pool = list(DEFAULT_AVAILABLE)
        for strategy in self.adapter.memory_alternatives(session):
            if strategy not in pool:
                pool.append(strategy)
        return pool

    def _execute(
        self,
        session: DebugSession,
        workspace: Path,
        *,
        execute_fn: Optional[RepairExecuteFn] = None,
        validator: Optional[ValidateFn] = None,
    ) -> dict[str, Any]:
        """执行修复 (缺省确定性桩; 注入器优先; 失败安全)。"""
        start = time.perf_counter()
        fn = execute_fn if execute_fn is not None else _production_default_execute_fn()
        try:
            outcome = fn(session, workspace) or {}
        except Exception as exc:  # noqa: BLE001 — 失败安全: 执行异常 → 失败
            outcome = {"success": False, "error": str(exc)}
        if not isinstance(outcome, dict):
            outcome = {"success": False, "error": "execute_fn 返回非 dict"}
        ok = bool(outcome.get("success"))
        validation = outcome.get("validation")
        # S10-071 P0-2: 生产默认真实验证 (真实 pytest), 注入 validator 优先 (测试 seam)
        active_validator = validator if validator is not None else _production_default_validator_fn()
        if active_validator is not None:
            try:
                # 兼容签名: 新 (session, outcome, *, workspace) / 旧 (session, result)
                import inspect as _inspect
                try:
                    _sig = _inspect.signature(active_validator)
                    _accepts_ws = "workspace" in _sig.parameters or any(
                        p.kind == _inspect.Parameter.VAR_KEYWORD for p in _sig.parameters.values())
                except (TypeError, ValueError):
                    _accepts_ws = True
                if _accepts_ws:
                    verdict = active_validator(session, outcome, workspace=workspace)
                else:
                    verdict = active_validator(session, outcome)
                if hasattr(verdict, "to_dict"):
                    validation = verdict.to_dict()
                    ok = bool(validation.get("success", ok))
                elif isinstance(verdict, dict):
                    validation = verdict
                    ok = bool(verdict.get("success", ok))
                else:
                    ok = bool(verdict)
                    validation = {"success": ok}
            except Exception:  # noqa: BLE001 — 验证异常 → 用执行结果
                pass
        if "validation_command" in outcome and not session.validation_command:
            session.validation_command = str(outcome.get("validation_command") or "")
        session.validation_result = validation if validation is not None else {"success": ok}
        return {
            "success": ok,
            "validation": session.validation_result,
            "cost": float(outcome.get("cost") or 0.0),
            "latency": time.perf_counter() - start,
            "outcome": outcome,
        }
