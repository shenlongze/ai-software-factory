"""factory-console/session/actions_debug.py — 调试/诊断动作 (R1, v1.1.254).

从 actions.py 拆出: 失败分析/历史/推荐/会话/根因/修复/校验/恢复 (自包含)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .action import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    ActionResult,
    ExecutionContext,
)


def _debug_params(context) -> dict:
    """取 debug action 参数 (intent.params 优先; 兼容测试 FakeContext.params)。"""
    intent = getattr(context, "intent", None)
    if intent is not None and getattr(intent, "params", None):
        return intent.params
    return getattr(context, "params", None) or {}


def _debug_workspace(context) -> Path:
    """debug action 工作区 (context.workspace 缺省 → ~/.factory)。"""
    return Path(getattr(context, "workspace", None) or DEFAULT_WORKSPACE)


def _debug_latest_failure(ws: Path) -> Optional[dict]:
    """最近失败任务 (缺省参数面): workspace/exec/execution_records.json 最新
    result=failed 记录 → {error_message, task_id, context}; 无 → None (失败安全)。"""
    try:
        records_file = ws / "exec" / "execution_records.json"
        data = json.loads(records_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → None
        return None
    if not isinstance(data, list):
        return None
    failed = [
        r for r in data
        if isinstance(r, dict) and str(r.get("result") or "").lower()
        in ("failed", "fail", "error")
    ]
    if not failed:
        return None
    failed.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
    record = failed[0]
    task = str(record.get("task") or "")
    return {
        "error_message": str(record.get("error") or "") or f"任务失败: {task}",
        "task_id": task,
        "context": str(record.get("intent") or ""),
    }


def debug_analyze(context: ExecutionContext) -> ActionResult:
    """调试分析 (S10-068): \"分析错误/为什么失败/debug\" → DebugDecision
    (错误类型 → 根因 → 历史经验 → 修复策略)。error_message 缺省 → 最近失败任务。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        from .debug import DebugEngine
        from .debug.error_analysis import ErrorAnalyzer

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        case_kw: dict = {
            "task_id": str(params.get("task_id") or ""),
            "agent_id": str(params.get("agent_id") or ""),
            "context": str(params.get("context") or ""),
            "project": str(params.get("project") or ""),
        }
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
            case_kw["task_id"] = case_kw["task_id"] or latest["task_id"]
            case_kw["context"] = case_kw["context"] or latest["context"]
        case = ErrorAnalyzer().extract(error_message, **case_kw)
        decision = engine.analyze(case)
        lines = [
            "调试分析:",
            f"• 错误类型: {case.error_type}",
            f"• 错误信息: {case.error_message[:200]}",
        ]
        for evidence in decision.evidence[:5]:
            lines.append(f"• 证据: {evidence}")
        strategy = decision.strategy.value if hasattr(decision.strategy, "value") else str(decision.strategy)
        lines.append(f"• 策略: {strategy} — {decision.reason} (conf {decision.confidence})")
        lines.append(f"• 相关经验: {len(decision.related_experiences)} 条")
        # S10-070: Audit 自动接入 (失败安全)
        try:
            from ..audit.audit_emitter import AuditEmitter
            AuditEmitter(workspace=ws).emit(
                "DEBUG_STARTED", project_id=context.project or "",
                task_id=str(params.get("task_id") or ""),
                agent_id=str(params.get("agent_id") or ""),
                actor_type="user", actor_id=str(getattr(context, "user", "") or ""),
                decision_reason=f"调试分析: {error_message or '最近失败'}",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data=decision.to_dict(),
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试分析失败: {exc}", error=str(exc))


def debug_history(context: ExecutionContext) -> ActionResult:
    """调试历史 (S10-068): \"查看调试经验/debug历史\" → debug_cases.json 历史。"""
    context.require("user")
    params = _debug_params(context)
    try:
        from .debug import DebugEngine

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        limit = int(params.get("limit") or 20)
        entries = engine.history(ws, limit=limit)
        lines = [f"调试历史 (共 {len(entries)} 条):"]
        for entry in entries:
            case = entry.get("case") or {}
            decision = entry.get("decision") or {}
            outcome = str(entry.get("outcome") or "pending")
            lines.append(
                f"• [{case.get('error_type') or 'UNKNOWN'}] "
                f"{(case.get('error_message') or '')[:60]} "
                f"→ {decision.get('strategy')} "
                f"(conf {decision.get('confidence')}, outcome: {outcome})"
            )
        if not entries:
            lines.append("无调试记录。")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data={"count": len(entries)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试历史查询失败: {exc}", error=str(exc))


def debug_recommend(context: ExecutionContext) -> ActionResult:
    """修复建议 (S10-068): \"修复建议/debug推荐\" → 策略推荐 (同 analyze 简版)。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        from .debug import DebugEngine
        from .debug.error_analysis import ErrorAnalyzer

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
        decision = engine.analyze(ErrorAnalyzer().extract(error_message))
        strategy = decision.strategy.value if hasattr(decision.strategy, "value") else str(decision.strategy)
        lines = [
            f"修复建议: {strategy} — {decision.reason} (conf {decision.confidence})",
        ]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"strategy": strategy, "reason": decision.reason,
                  "confidence": decision.confidence},
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"修复建议失败: {exc}", error=str(exc))


def debug_stats(context: ExecutionContext) -> ActionResult:
    """调试统计 (S10-068): \"debug统计/调试统计\" → 按错误类型/策略/结果统计。"""
    context.require("user")
    try:
        from .debug import DebugEngine

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        stats = engine.stats(ws)
        lines = [f"调试统计 (共 {stats['total_cases']} 个案件):"]
        by_error_type = stats["by_error_type"] or {}
        if by_error_type:
            lines.append("按错误类型: " + ", ".join(
                f"{k}={v}" for k, v in by_error_type.items()))
        else:
            lines.append("按错误类型: 无")
        by_strategy = stats["by_strategy"] or {}
        if by_strategy:
            lines.append("按策略: " + ", ".join(
                f"{k}={v}" for k, v in by_strategy.items()))
        else:
            lines.append("按策略: 无")
        by_outcome = stats["by_outcome"]
        lines.append(f"按结果: 成功 {by_outcome['success']}, "
                     f"失败 {by_outcome['fail']}, 待定 {by_outcome['pending']}")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=stats)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试统计失败: {exc}", error=str(exc))


# ================================================================== S10-068 Part 2 Autonomous Debug & Repair CLI

def _debug_pipeline(context) -> Any:
    """DebugPipeline 实例 (工作区同 debug action 口径)。"""
    from .debug import DebugPipeline

    return DebugPipeline(_debug_workspace(context))


def _debug_require_session(context, params) -> tuple[Any, Optional[dict]]:
    """按 debug_id 取会话 (缺省 → 最近会话; 无 → (None, None))。"""
    pipeline = _debug_pipeline(context)
    debug_id = str(params.get("debug_id") or "").strip()
    if debug_id:
        session = pipeline.store.get(debug_id)
        return (pipeline, session.to_dict() if session is not None else None)
    latest = pipeline.store.list(limit=1)
    if not latest:
        return (pipeline, None)
    return (pipeline, latest[0].to_dict())


def debug_session(context: ExecutionContext) -> ActionResult:
    """开始调试 (S10-068 Part 2): \"开始调试/调试会话\" → DebugSession (ANALYZING)。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        ws = _debug_workspace(context)
        pipeline = _debug_pipeline(context)
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
            params.setdefault("task_id", latest.get("task_id") or "")
            params.setdefault("context", latest.get("context") or "")
        session = pipeline.start(
            project_id=str(params.get("project_id") or ""),
            task_id=str(params.get("task_id") or ""),
            agent_id=str(params.get("agent_id") or ""),
            error_message=error_message,
            failure_id=str(params.get("failure_id") or ""),
            context=str(params.get("context") or ""),
        )
        lines = [
            "调试会话已开始:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
            f"• 错误: {session.error_summary[:200]}",
            "下一步: debug analyze / debug root-cause 分析根因",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试会话启动失败: {exc}", error=str(exc))


def debug_root_cause(context: ExecutionContext) -> ActionResult:
    """根因分析 (S10-068 Part 2): \"找一下根因\" → RootCause (9 类根因类型)。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        ws = _debug_workspace(context)
        pipeline = _debug_pipeline(context)
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
        case = pipeline.engine.analyzer.extract(
            error_message, task_id=str(params.get("task_id") or ""))
        root = pipeline.engine.root_cause_analyzer.analyze(case)
        lines = [
            "根因分析:",
            f"• 根因类型: {root.root_cause_type}",
            f"• 根因: {root.cause}",
            f"• 置信度: {root.confidence:.2f}",
            f"• 推理: {root.reasoning_summary}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=root.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"根因分析失败: {exc}", error=str(exc))


def debug_repair(context: ExecutionContext) -> ActionResult:
    """自动修复 (S10-068 Part 2): \"自动修复\" → RepairSafety 治理闸后执行修复。"""
    context.require("user")
    params = _debug_params(context)
    try:
        pipeline, session_dict = _debug_require_session(context, params)
        if session_dict is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="无调试会话 (先执行 debug session / debug analyze)",
                error="no debug session",
            )
        from .debug.debug_session import DebugSession, SESSION_ANALYZING

        session = DebugSession.from_dict(session_dict)
        if session.status == SESSION_ANALYZING:
            session = pipeline.analyze(session)
        session = pipeline.repair(
            session,
            max_attempts=int(params.get("max_attempts") or 3),
        )
        decision = (session.budget_usage or {}).get("decision", "")
        lines = [
            "自动修复:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
            f"• 决策: {decision} — {(session.budget_usage or {}).get('reason', '')}",
            f"• 策略: {session.selected_strategy} (第 {session.attempt_number} 次尝试)",
        ]
        if session.status == "WAITING_FOR_REVIEW":
            lines.append("• 需人工审批: debug resume (decision=approved) 继续")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"自动修复失败: {exc}", error=str(exc))


def debug_validate(context: ExecutionContext) -> ActionResult:
    """验证修复 (S10-068 Part 2): \"验证修复\" → PASS→SUCCESS / FAIL→RETRYING。"""
    context.require("user")
    params = _debug_params(context)
    try:
        pipeline, session_dict = _debug_require_session(context, params)
        if session_dict is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="无调试会话 (先执行 debug session / debug repair)",
                error="no debug session",
            )
        from .debug.debug_session import DebugSession

        result = params.get("result")
        if result is not None and not isinstance(result, bool):
            result = str(result).strip().lower() in (
                "success", "pass", "passed", "true", "1", "ok", "succeeded", "成功")
        session = pipeline.validate(
            DebugSession.from_dict(session_dict),
            result=result,
            validation_command=str(params.get("validation_command") or ""),
        )
        lines = [
            "验证修复:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
            f"• 验证结果: {session.validation_result}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试验证失败: {exc}", error=str(exc))


def debug_resume(context: ExecutionContext) -> ActionResult:
    """继续调试 (S10-068 Part 2): \"继续调试\" → REVIEW 通过后继续 (approved 默认)。"""
    context.require("user")
    params = _debug_params(context)
    try:
        pipeline, session_dict = _debug_require_session(context, params)
        if session_dict is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="无调试会话 (先执行 debug session / debug repair)",
                error="no debug session",
            )
        from .debug.debug_session import DebugSession

        session = pipeline.resume(
            DebugSession.from_dict(session_dict),
            decision=str(params.get("decision") or "approved"),
        )
        lines = [
            "继续调试:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试继续失败: {exc}", error=str(exc))


# ================================================================== S10-069 Audit Intelligence CLI
