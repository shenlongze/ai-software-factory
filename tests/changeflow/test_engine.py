"""tests/changeflow/test_engine.py — ChangeWorkflowEngine: evaluate → _launch →
workflow_chain (Phase 6E, ADR-0020)。

覆盖:
- evaluate: 无 task store / 任务不存在 → ERROR; 无匹配触发器 → SKIP;
  规则 FAIL → FAIL 不触发; 规则 PASS → 触发 run (execute 语义);
  executor 执行 + completed 事件。
- build_context: 规则输入装配 (validation/commits/files/required_files/
  runtime_pref/available) + 失败安全。
- matching_triggers: 项目/类型过滤。
- _launch: 目标工作流未注册 / 任务已有 run → 失败转 ERROR 评估 (不级联);
  run CREATED→RUNNING + 第一步 RUNNING + 落盘 + started 事件。
- workflow_chain: 空链 / 任务工作流行 / 触发行 / 合并。
- _outcome_status: executor 结果 → 终态判定。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from events.models import EventType
from workflows.models import WorkflowRun, WorkflowStatus

from changeflow.engine import ChangeFlowError, ChangeWorkflowEngine
from changeflow.models import ChangeEvaluation, ChangeTrigger

from changeflow_helpers import make_task, make_trigger, make_workflow


# ------------------------------------------------------------------ stub change service

class StubChangeService:
    """鸭子类型 ChangeService (validate/analyze 返回固定快照; 可注入异常)。"""

    def __init__(self, status: str | None = "PASS",
                 files: list[str] | None = None,
                 commits: list[str] | None = None,
                 error: Exception | None = None) -> None:
        self._status = status
        self._files = files or []
        self._commits = commits or []
        self._error = error

    def validate(self, task_id: str):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(status=self._status)

    def analyze(self, task_id: str):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(files=self._files, commits=self._commits)


def ok_outcome(status: str = "COMPLETED"):
    return SimpleNamespace(status=WorkflowStatus.parse(status))


class TestEvaluateBasics:
    def test_no_task_store_error(self):
        engine = ChangeWorkflowEngine()  # 零装配: task store 缺失
        evaluation = engine.evaluate("MP-BUG-001")
        assert evaluation.status == "ERROR"
        assert "no task store" in evaluation.error

    def test_task_not_found_error(self, engine):
        evaluation = engine.evaluate("MP-NOPE-000")
        assert evaluation.status == "ERROR"
        assert "task not found" in evaluation.error
        assert evaluation.trigger_id is None

    def test_no_matching_trigger_skip(self, engine, task_store):
        task_store.create(make_task(task_id="MP-BUG-001", type_="bug"))
        evaluation = engine.evaluate("MP-BUG-001")
        assert evaluation.status == "SKIP"
        assert evaluation.trigger_id is None
        assert evaluation.rules == []
        assert "无匹配触发器" in evaluation.error

    def test_skip_still_emits_evaluated_event(self, engine, task_store, event_store):
        task_store.create(make_task(task_id="MP-BUG-001", type_="bug"))
        engine.evaluate("MP-BUG-001")
        events = event_store.query(event_type=EventType.CHANGE_TRIGGER_EVALUATED)
        assert len(events) == 1
        assert events[0].result == "SKIP"

    def test_returns_change_evaluation_type(self, engine, task_store):
        task_store.create(make_task())
        evaluation = engine.evaluate("MP-BUG-001")
        assert isinstance(evaluation, ChangeEvaluation)


class TestEvaluateRulesStatus:
    def test_all_rules_skip_no_trigger(self, engine, task_store):
        """匹配触发器但 4 规则全 SKIP (无证据) → 评估 SKIP 不触发。"""
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        evaluation = engine.evaluate("MP-BUG-001")
        assert evaluation.status == "SKIP"
        assert evaluation.trigger_id == "TRIG-FEATURE-RELEASE"
        assert len(evaluation.rules) == 4
        assert evaluation.triggered_workflow is None

    def test_validation_fail_no_trigger(self, engine, task_store):
        change = StubChangeService(status="FAIL")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=engine.workflow_engine.store,
            change_service=change, logger=engine.logger,
        )
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        evaluation = engine.evaluate("MP-BUG-001")
        assert evaluation.status == "FAIL"
        assert evaluation.triggered_workflow is None
        assert evaluation.rules[0].status == "FAIL"

    def test_fail_rule_breakdown_present(self, engine, task_store):
        change = StubChangeService(status="FAIL", commits=["abc123"])
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            change_service=change, logger=engine.logger,
        )
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        evaluation = engine.evaluate("MP-BUG-001")
        assert [r.status for r in evaluation.rules] == ["FAIL", "PASS", "SKIP", "SKIP"]


class TestEvaluateTrigger:
    def test_pass_triggers_run_without_executor(self, engine, task_store,
                                                workflow_store):
        """PASS + 显式 execute=True (无 executor) → 触发 run (CREATED→RUNNING) 但不执行。"""
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        evaluation = engine.evaluate("MP-BUG-001", execute=True)
        assert evaluation.status == "PASS"
        assert evaluation.triggered_workflow == "release"
        assert evaluation.run_id is not None

        run = workflow_store.get_run_by_task("MP-BUG-001")
        assert run is not None
        assert run.status == WorkflowStatus.RUNNING
        assert run.step_states[0].status.value == "RUNNING"

    def test_pass_triggers_started_event(self, engine, task_store,
                                         workflow_store, event_store):
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        engine.evaluate("MP-BUG-001", execute=True)
        started = event_store.query(event_type=EventType.CHANGE_WORKFLOW_STARTED)
        assert len(started) == 1
        assert started[0].payload["workflow_id"] == "release"
        assert started[0].payload["run_id"] is not None

    def test_execute_false_no_trigger(self, engine, task_store, workflow_store):
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        evaluation = engine.evaluate("MP-BUG-001", execute=False)
        assert evaluation.status == "PASS"
        assert evaluation.triggered_workflow is None
        assert evaluation.run_id is None
        assert workflow_store.get_run_by_task("MP-BUG-001") is None

    def test_executor_runs_and_emits_completed(self, engine, task_store,
                                               workflow_store, event_store):
        calls: list[str] = []
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")

        def executor(task_id: str):
            calls.append(task_id)
            return ok_outcome("COMPLETED")

        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, executor=executor, logger=engine.logger,
        )
        evaluation = engine.evaluate("MP-BUG-001")
        assert evaluation.status == "PASS"
        assert calls == ["MP-BUG-001"]
        completed = event_store.query(event_type=EventType.CHANGE_WORKFLOW_COMPLETED)
        assert len(completed) == 1
        assert completed[0].payload["result"] == "COMPLETED"

    def test_executor_failed_outcome_still_pass_evaluation(self, engine,
                                                           task_store,
                                                           workflow_store,
                                                           event_store):
        """执行终态 FAILED 只审计 (completed result=FAILED), 评估仍 PASS。"""
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")

        def executor(task_id: str):
            return ok_outcome("FAILED")

        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, executor=executor, logger=engine.logger,
        )
        evaluation = engine.evaluate("MP-BUG-001")
        assert evaluation.status == "PASS"
        completed = event_store.query(event_type=EventType.CHANGE_WORKFLOW_COMPLETED)
        assert completed[0].payload["result"] == "FAILED"

    def test_matching_trigger_selection_first(self, engine, task_store):
        """多个命中触发器 → 取第一个 (注册表按 id 排序)。"""
        engine.triggers.register(make_trigger(trigger_id="TRIG-A",
                                              target_workflow="wf-a"))
        engine.triggers.register(make_trigger(trigger_id="TRIG-B",
                                              target_workflow="wf-b"))
        task_store.create(make_task())
        evaluation = engine.evaluate("MP-BUG-001")
        assert evaluation.trigger_id == "TRIG-A"


class TestBuildContext:
    def test_no_change_service_all_empty(self, engine, task_store):
        task_store.create(make_task())
        task = task_store.get("MP-BUG-001")
        ctx = engine.build_context(task, make_trigger())
        assert ctx.validation_status is None
        assert ctx.linked_commits == []
        assert ctx.changed_files == []
        assert ctx.required_files == []
        assert ctx.runtime_pref is None
        assert ctx.available_runtimes == set()

    def test_validation_status_assembled(self, task_store):
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(task_store=task_store,
                                      change_service=change)
        task_store.create(make_task())
        ctx = engine.build_context(task_store.get("MP-BUG-001"), make_trigger())
        assert ctx.validation_status == "PASS"
        assert ctx.required_validation == "PASS"

    def test_commits_and_files_assembled(self, task_store):
        change = StubChangeService(status="PASS",
                                   files=["app/auth.py"],
                                   commits=["abc123", "def456", "abc123"])
        engine = ChangeWorkflowEngine(task_store=task_store,
                                      change_service=change)
        task_store.create(make_task())
        ctx = engine.build_context(task_store.get("MP-BUG-001"), make_trigger())
        assert ctx.changed_files == ["app/auth.py"]
        assert ctx.linked_commits == ["abc123", "def456"]  # 保序去重

    def test_required_files_by_task_type(self, task_store):
        engine = ChangeWorkflowEngine(
            task_store=task_store,
            required_files_map={"feature": ["CHANGELOG.md"]})
        task_store.create(make_task())
        ctx = engine.build_context(task_store.get("MP-BUG-001"), make_trigger())
        assert ctx.required_files == ["CHANGELOG.md"]

    def test_required_files_by_trigger_id_wins(self, task_store):
        engine = ChangeWorkflowEngine(
            task_store=task_store,
            required_files_map={
                "TRIG-FEATURE-RELEASE": ["VERSION"],
                "feature": ["CHANGELOG.md"],
            })
        task_store.create(make_task())
        ctx = engine.build_context(task_store.get("MP-BUG-001"),
                                   make_trigger(trigger_id="TRIG-FEATURE-RELEASE"))
        assert ctx.required_files == ["VERSION"]

    def test_runtime_pref_and_available(self, task_store, runtime_store):
        from runtime.models import RuntimeInfo, RuntimeStatus

        runtime_store.save_runtime(RuntimeInfo(id="echo", name="Echo Runtime",
                                               type="mock",
                                               status=RuntimeStatus.AVAILABLE))
        from runtime.registry import RuntimeRegistry

        engine = ChangeWorkflowEngine(
            task_store=task_store,
            runtime_registry=RuntimeRegistry(runtime_store),
            project_runtime_prefs={"markpad": "echo"})
        task_store.create(make_task())
        ctx = engine.build_context(task_store.get("MP-BUG-001"), make_trigger())
        assert ctx.runtime_pref == "echo"
        assert ctx.available_runtimes == {"echo"}

    def test_change_service_exception_fail_safe(self, task_store):
        change = StubChangeService(error=RuntimeError("git exploded"))
        engine = ChangeWorkflowEngine(task_store=task_store,
                                      change_service=change)
        task_store.create(make_task())
        ctx = engine.build_context(task_store.get("MP-BUG-001"), make_trigger())
        assert ctx.validation_status is None  # 异常 → 规则① SKIP
        assert ctx.linked_commits == []
        assert ctx.changed_files == []


class TestMatchingTriggers:
    def test_empty_registry(self, engine, task_store):
        task_store.create(make_task())
        assert engine.matching_triggers(task_store.get("MP-BUG-001")) == []

    def test_project_filter(self, engine, task_store):
        engine.triggers.register(make_trigger(project_id="markpad"))
        task_store.create(make_task())  # project=markpad
        matched = engine.matching_triggers(task_store.get("MP-BUG-001"))
        assert [t.id for t in matched] == ["TRIG-FEATURE-RELEASE"]

    def test_project_mismatch(self, engine, task_store):
        engine.triggers.register(make_trigger(project_id="other"))
        task_store.create(make_task())  # project=markpad
        assert engine.matching_triggers(task_store.get("MP-BUG-001")) == []

    def test_task_type_filter(self, engine, task_store):
        engine.triggers.register(make_trigger(task_type="feature"))
        task_store.create(make_task())  # type=feature
        assert len(engine.matching_triggers(task_store.get("MP-BUG-001"))) == 1
        task_store.create(make_task(task_id="MP-BUG-002", type_="bug"))
        assert engine.matching_triggers(task_store.get("MP-BUG-002")) == []

    def test_wildcard_matches_all(self, engine, task_store):
        engine.triggers.register(make_trigger())
        task_store.create(make_task(task_id="MP-BUG-001"))
        task_store.create(make_task(task_id="MP-BUG-002", type_="bug"))
        assert len(engine.matching_triggers(task_store.get("MP-BUG-002"))) == 1


class TestLaunchFailures:
    def test_target_workflow_not_registered_error_evaluation(self, engine,
                                                             task_store):
        """目标工作流未注册 → 触发失败 → ERROR 评估 (不级联, 不抛)。"""
        engine.triggers.register(make_trigger(target_workflow="ghost"))
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=engine.workflow_engine.store,
            change_service=change, logger=engine.logger,
        )
        evaluation = engine.evaluate("MP-BUG-001", execute=True)
        assert evaluation.status == "ERROR"
        assert evaluation.triggered_workflow is None
        assert "not registered" in evaluation.error
        assert "ghost" in evaluation.error

    def test_task_already_has_run_error_evaluation(self, engine, task_store,
                                                   workflow_store):
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        # 预置既有 run
        wf = workflow_store.get_workflow("release")
        run = WorkflowRun.from_workflow(run_id="WR-OLD", workflow=wf,
                                        task_id="MP-BUG-001")
        workflow_store.save_run(run)

        evaluation = engine.evaluate("MP-BUG-001", execute=True)
        assert evaluation.status == "ERROR"
        assert "already has a workflow run" in evaluation.error
        assert "WR-OLD" in evaluation.error

    def test_launch_failure_emits_evaluated_error_event(self, engine,
                                                        task_store,
                                                        event_store):
        engine.triggers.register(make_trigger(target_workflow="ghost"))
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=engine.workflow_engine.store,
            change_service=change, logger=engine.logger,
        )
        engine.evaluate("MP-BUG-001", execute=True)
        events = event_store.query(event_type=EventType.CHANGE_TRIGGER_EVALUATED)
        assert events[0].result == "ERROR"
        assert events[0].payload["error"] is not None


class TestLaunchRun:
    def test_run_created_running_first_step(self, engine, task_store,
                                            workflow_store, event_store):
        workflow_store.save_workflow(make_workflow(steps=("build", "publish")))
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        evaluation = engine.evaluate("MP-BUG-001", execute=True)
        run = workflow_store.get_run_by_task("MP-BUG-001")
        assert run.workflow_id == "release"
        assert run.run_id == evaluation.run_id
        assert run.status == WorkflowStatus.RUNNING
        statuses = [st.status.value for st in run.step_states]
        assert statuses == ["RUNNING", "PENDING"]

    def test_next_run_id_increments(self, engine, task_store, workflow_store):
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        task_store.create(make_task(task_id="MP-BUG-002"))
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        e1 = engine.evaluate("MP-BUG-001", execute=True)
        e2 = engine.evaluate("MP-BUG-002", execute=True)
        assert e1.run_id != e2.run_id


class TestWorkflowChain:
    def test_empty_chain(self, engine):
        assert engine.workflow_chain("MP-NOPE-000") == []

    def test_task_workflow_row(self, engine, task_store, workflow_store):
        workflow_store.save_workflow(make_workflow(workflow_id="feature-delivery",
                                                   steps=("plan", "dev")))
        task_store.create(make_task(workflow="feature-delivery"))
        chain = engine.workflow_chain("MP-BUG-001")
        assert len(chain) == 1
        row = chain[0]
        assert row["task_id"] == "MP-BUG-001"
        assert row["workflow_id"] == "feature-delivery"
        assert row["triggered"] is False
        assert row["status"] == "NOT_STARTED"

    def test_triggered_workflow_row(self, engine, task_store, workflow_store,
                                    event_store):
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task())
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        engine.evaluate("MP-BUG-001", execute=True)
        chain = engine.workflow_chain("MP-BUG-001")
        rows = [r for r in chain if r["triggered"]]
        assert len(rows) == 1
        assert rows[0]["workflow_id"] == "release"
        assert rows[0]["trigger_id"] == "TRIG-FEATURE-RELEASE"
        assert rows[0]["status"] == "STARTED"

    def test_chain_combines_task_and_triggered(self, engine, task_store,
                                               workflow_store):
        workflow_store.save_workflow(make_workflow(workflow_id="feature-delivery",
                                                   steps=("plan", "dev")))
        workflow_store.save_workflow(make_workflow())
        engine.triggers.register(make_trigger())
        task_store.create(make_task(workflow="feature-delivery"))
        change = StubChangeService(status="PASS")
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_engine=engine.workflow_engine,
            workflow_store=workflow_store,
            change_service=change, logger=engine.logger,
        )
        engine.evaluate("MP-BUG-001", execute=True)
        chain = engine.workflow_chain("MP-BUG-001")
        assert len(chain) == 2
        assert sum(1 for r in chain if r["triggered"]) == 1
        assert sum(1 for r in chain if not r["triggered"]) == 1

    def test_task_run_status_reflected(self, engine, task_store,
                                       workflow_store):
        workflow_store.save_workflow(make_workflow(workflow_id="feature-delivery",
                                                   steps=("plan", "dev")))
        task_store.create(make_task(workflow="feature-delivery"))
        engine = ChangeWorkflowEngine(
            triggers=engine.triggers, task_store=task_store,
            workflow_store=workflow_store,
        )
        # 预置运行实例 (RUNNING)
        wf = workflow_store.get_workflow("feature-delivery")
        run = WorkflowRun.from_workflow(run_id="WR-1", workflow=wf,
                                        task_id="MP-BUG-001")
        run.status = WorkflowStatus.RUNNING
        workflow_store.save_run(run)
        chain = engine.workflow_chain("MP-BUG-001")
        assert chain[0]["run_id"] == "WR-1"
        assert chain[0]["status"] == "RUNNING"


class TestOutcomeStatus:
    def test_none_outcome_completed(self):
        assert ChangeWorkflowEngine._outcome_status(None) == "COMPLETED"

    def test_status_enum_value(self):
        assert ChangeWorkflowEngine._outcome_status(
            SimpleNamespace(status=WorkflowStatus.COMPLETED)) == "COMPLETED"
        assert ChangeWorkflowEngine._outcome_status(
            SimpleNamespace(status=WorkflowStatus.FAILED)) == "FAILED"

    def test_status_string_value(self):
        assert ChangeWorkflowEngine._outcome_status(
            SimpleNamespace(status="COMPLETED")) == "COMPLETED"

    def test_ok_boolean_fallback(self):
        assert ChangeWorkflowEngine._outcome_status(
            SimpleNamespace(ok=True)) == "COMPLETED"
        assert ChangeWorkflowEngine._outcome_status(
            SimpleNamespace(ok=False)) == "FAILED"
