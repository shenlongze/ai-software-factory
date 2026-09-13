"""understanding/events.py — understanding.* 审计事件辅助 (经 EventLogger, Phase 7, ADR-0021)。

设计依据:
- phase7-plan.md §3: understanding.started / understanding.completed /
  understanding.failed 事件; 可选细粒度 (stage.detected/artifact.detected) 未启用
  (KISS, 报告 payload 已含同等信息)。
- ADR-0002: 所有 CLI 行为必须产生 Event; 事件类型扩展 = 加 EventType 枚举成员
  (ADR-0001 决策 1, 不改表结构)。CLI 读命令经 source="cli" 发 understanding.viewed
  (同 dashboard.viewed 模式)。
- 只读铁律: 本模块只发审计事件, 不触碰任何业务状态/文件写操作。

payload 契约 (Dashboard Understanding View 事件聚合与 CLI --json 出口一致):
- understanding.started: path
- understanding.completed: path/stage/confidence/artifacts/missing
- understanding.failed: path/error
- understanding.viewed: path/stage/confidence/artifacts_present/artifacts_missing
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType


def record_understanding_started(
    logger: Any,
    *,
    path: str,
    source: str = "understanding",
) -> Event | None:
    """项目分析开始 (UnderstandingService.analyze 装配, 校验通过后)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.UNDERSTANDING_STARTED,
        source=source,
        stage="started",
        action="analyze project understanding",
        result="OK",
        payload={"path": str(path)},
    )


def record_understanding_completed(
    logger: Any,
    *,
    report: Any,
    source: str = "understanding",
) -> Event | None:
    """项目分析完成 (payload: path/stage/confidence/artifacts/missing)。"""
    if logger is None:
        return None
    artifacts = [a.artifact for a in report.artifacts if a.present]
    return logger.record(
        EventType.UNDERSTANDING_COMPLETED,
        source=source,
        stage=report.stage.stage,
        action="analyze project understanding",
        result="OK",
        payload={
            "path": report.path,
            "stage": report.stage.stage,
            "confidence": report.stage.confidence,
            "artifacts": artifacts,
            "missing": report.missing.missing,
        },
    )


def record_understanding_failed(
    logger: Any,
    *,
    path: str,
    error: Any,
    source: str = "understanding",
) -> Event | None:
    """项目分析失败 (路径无效/内部异常; result=ERROR)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.UNDERSTANDING_FAILED,
        source=source,
        stage="failed",
        action="analyze project understanding",
        result="ERROR",
        payload={"path": str(path), "error": str(error)},
    )


def record_understanding_viewed(
    logger: Any,
    *,
    path: str,
    stage: str,
    confidence: float,
    present: int,
    missing: int,
    source: str = "cli",
) -> Event | None:
    """理解报告被查看 (CLI 读命令审计, ADR-0002; source 缺省 cli)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.UNDERSTANDING_VIEWED,
        source=source,
        stage=stage,
        action="view project understanding",
        result="OK",
        payload={
            "path": str(path),
            "stage": stage,
            "confidence": confidence,
            "artifacts_present": present,
            "artifacts_missing": missing,
        },
    )
