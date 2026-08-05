"""validation/engine.py — ValidationEngine: 三层验证编排 + Event 集成。

设计依据:
- phase3a-status.md: ValidationEngine.validate(task_id) → ValidationReport
- 父任务事件流程 (铁律, 所有验证行为经 EventLogger):
    validation.started → validation.rule.started → validation.rule.completed (×规则)
    → validation.completed; 失败追加 validation.failed
- L1 Factory / L2 Workflow / L3 Artifact Hook 三层始终执行;
  --level 保留为事件 stage 标记 (cli-design 兼容, 见 ADR-0003)。

规则为纯函数 (rules.py); 引擎负责: 装载任务数据 → 逐规则执行
(异常兜底为 ERROR, 不中断) → 汇总报告 → 发布事件。
"""

from __future__ import annotations

from typing import Any

from events.logger import EventLogger
from events.models import EventType
from tasks.models import TaskStatus
from tasks.store import TaskStore

from . import rules
from .models import ValidationResult, ValidationStatus
from .reports import ValidationReport, render_checks

# 验证事件流: started → rule.started → rule.completed → completed; 失败追加 failed
_RULE_ORDER = (
    ("L1", "task_exists"),
    ("L1", "task_data"),
    ("L1", "task_status"),
    ("L1", "task_files"),
    ("L2", "workflow"),
    ("L2", "expect_status"),  # 仅 --expect-status 时执行
    ("L3", "artifact"),
)


class ValidationEngine:
    """三层验证引擎。构造需 TaskStore (任务文件) + EventLogger (事件铁律)。"""

    def __init__(
        self, task_store: TaskStore, logger: EventLogger, source: str = "validation_engine",
    ):
        self._tasks = task_store
        self._logger = logger
        self._source = source
        self._task_id = ""
        self._project_id: str | None = None

    # ------------------------------------------------------------------ 主流程

    def validate(
        self,
        task_id: str,
        *,
        level: str = "L2",
        expect_status: TaskStatus | None = None,
    ) -> ValidationReport:
        """对任务执行三层验证, 全程经 EventLogger 发布事件, 返回汇总报告。"""
        self._task_id = task_id
        planned = [f"{lvl}.{rule}" for lvl, rule in _RULE_ORDER
                   if rule != "expect_status" or expect_status is not None]

        self._record(
            EventType.VALIDATION_STARTED, stage=level, result="started",
            action="run validation",
            payload={
                "level": level,
                "expect_status": expect_status.value if expect_status else None,
                "checks": planned,
            },
        )

        # 装载任务数据 (文件缺失/损坏 → task=None, L1 规则给出 FAIL/SKIP)
        data, task, error = rules.load_task_file(task_id, self._tasks.dir)
        self._project_id = task.project if task is not None else None

        results: list[ValidationResult] = []
        events = self._logger.store.query(task_id=task_id) if task is not None else []
        for lvl, rule in _RULE_ORDER:
            if rule == "expect_status" and expect_status is None:
                continue
            fn = getattr(rules, f"rule_{rule}")
            args: tuple[Any, ...]
            if rule == "task_exists":
                args = (task_id, self._tasks.dir / f"{task_id}.json")
            elif rule == "task_data":
                args = (task_id, data, error)
            elif rule in ("task_status", "task_files"):
                args = (task_id, data)
            elif rule == "workflow":
                args = (task_id, task, events)
            elif rule == "expect_status":
                args = (task_id, task, expect_status)
            else:  # artifact
                args = (task_id,)
            results.append(self._run_rule(lvl, rule, fn, *args))

        report = ValidationReport(
            task_id=task_id, level=level, results=results,
            task_found=(self._tasks.dir / f"{task_id}.json").exists(),
        )

        checks = render_checks(results)
        self._record(
            EventType.VALIDATION_COMPLETED, stage=level, result=report.result.value,
            action="validation completed",
            payload={"level": level,
                     "expect_status": expect_status.value if expect_status else None,
                     "reason": report.reason, "checks": checks},
        )
        if report.result is ValidationStatus.FAIL:
            self._record(
                EventType.VALIDATION_FAILED, stage=level, result="FAIL",
                action="validation failed",
                payload={"level": level, "reason": report.reason,
                         "failure_class": report.reason, "checks": checks},
            )
        return report

    # ------------------------------------------------------------------ 内部

    def _run_rule(self, level: str, rule: str, fn: Any, *args: Any) -> ValidationResult:
        """执行单条规则并发布 rule.started / rule.completed; 异常兜底为 ERROR。"""
        rule_id = f"{level}.{rule}"
        self._record(
            EventType.VALIDATION_RULE_STARTED, stage=level, result="started",
            action=f"run rule {rule_id}", payload={"rule": rule_id, "level": level},
        )
        try:
            result = fn(*args)
        except Exception as exc:  # 规则内部错误 → ERROR, 不中断整个验证
            result = ValidationResult(
                id=rule_id, task_id=self._task_id, level=level, rule=rule,
                status=ValidationStatus.ERROR, message=f"{type(exc).__name__}: {exc}",
            )
        self._record(
            EventType.VALIDATION_RULE_COMPLETED, stage=level, result=result.status.value,
            action=f"rule {rule_id} {result.status.value}",
            payload={"rule": rule_id, "level": level,
                     "status": result.status.value, "message": result.message},
        )
        return result

    def _record(
        self, type_: EventType, *, stage: str, result: str, action: str, payload: dict,
    ) -> Any:
        """统一经 EventLogger 发布事件 (铁律: 不绕过)。"""
        return self._logger.record(
            type_, source=self._source, project_id=self._project_id, task_id=self._task_id,
            stage=stage, result=result, action=action, payload=payload,
        )
