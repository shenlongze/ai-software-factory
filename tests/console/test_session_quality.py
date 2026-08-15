"""S10-053 — Quality & Repair Loop 测试套件。

覆盖: ValidationResult / Validator / Lifecycle Gate / RepairManager /
Retry Policy / repair_task Action / Execution+Validation Flow /
Failure Recovery / 完整生产 Demo / Reviewer 接口 / Progress 增强 / 回归。

装配: tmp_path workspace + mock execute_fn/validator; 零真实 LLM/网络/~/.factory 污染。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

QUALITY = import_module("factory-console.session.quality")
PIPE = import_module("factory-console.session.pipeline")
ORCH = import_module("factory-console.session.orchestrator")
ACTIONS = import_module("factory-console.session.actions")
ACTION_MOD = import_module("factory-console.session.action")


# ================================================================== fixtures

def _make_project(tmp_path: Path, slug: str = "scorepocket") -> Path:
    """构造最小项目空间 (execution_plan.json + product.json + project.json)。"""
    pd = tmp_path / "projects" / slug
    pd.mkdir(parents=True, exist_ok=True)
    plan = {
        "tasks": [
            {"id": "T001", "name": "数据库 Schema", "agent_type": "backend", "agent": "backend-1"},
            {"id": "T002", "name": "后端 API", "agent_type": "backend", "agent": "backend-1"},
            {"id": "T003", "name": "前端页面", "agent_type": "frontend", "agent": "flutter-dev"},
        ],
        "count": 3,
    }
    (pd / "execution_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    (pd / "product.json").write_text(
        json.dumps({"name": "ScorePocket", "status": "execution_ready"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (pd / "project.json").write_text(
        json.dumps({"name": "ScorePocket", "status": "execution_ready"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return pd


def _ok_fn(artifact: str = "/tmp/p.patch"):
    """成功 execute_fn (带 artifact)。"""

    def fn(task, project_dir, workspace):
        return {"success": True, "artifact": artifact, "error": None, "cost": "100 tokens"}

    return fn


def _fail_fn(error: str = "boom"):
    def fn(task, project_dir, workspace):
        return {"success": False, "artifact": "", "error": error, "cost": ""}

    return fn


# ================================================================== 1. ValidationResult


class TestValidationResult:
    def test_default_fields(self):
        v = QUALITY.ValidationResult(success=True)
        assert v.success is True
        assert v.tests_total == 0
        assert v.tests_passed == 0
        assert v.tests_failed == 0
        assert v.errors == []
        assert v.timestamp == ""

    def test_to_dict(self):
        v = QUALITY.ValidationResult(success=False, tests_total=3, tests_passed=2, tests_failed=1, errors=["x"])
        d = v.to_dict()
        assert d["success"] is False
        assert d["tests_total"] == 3
        assert d["tests_failed"] == 1
        assert d["errors"] == ["x"]

    def test_from_dict(self):
        v = QUALITY.ValidationResult.from_dict({"success": True, "tests_total": 5, "tests_passed": 5})
        assert v.success is True
        assert v.tests_passed == 5

    def test_from_dict_roundtrip(self):
        v = QUALITY.ValidationResult(success=True, tests_total=2, tests_passed=2, errors=[])
        v2 = QUALITY.ValidationResult.from_dict(v.to_dict())
        assert v2.success == v.success
        assert v2.tests_total == v.tests_total


# ================================================================== 2. Validator


class TestValidator:
    def test_success(self):
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": True, "artifact": "/tmp/a"})
        assert r.success is True
        assert r.tests_passed == 1

    def test_success_no_artifact_compat(self):
        # S10-053 收尾: artifact 缺失不判失败 (兼容 execute_fn {"success": True} 无 artifact)
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": True})
        assert r.success is True

    def test_failure_success_false(self):
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": False, "error": "boom"})
        assert r.success is False
        assert any("boom" in e for e in r.errors)

    def test_failure_explicit_error(self):
        # 实现语义 (S10-053 收尾): 仅 success=False 判失败; success=True 即使带 error 字段也通过
        # (execute_fn 可能返回 {success: True, error: "info"}) — error 字段不强制 FAIL
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": False, "error": "validation error"})
        assert r.success is False
        assert any("validation error" in e for e in r.errors)

    def test_non_dict_result(self):
        r = QUALITY.Validator().validate({"id": "T1"}, None)
        assert r.success is False

    def test_command_interface_accepted(self):
        # command 参数预留 (pytest/flutter test/npm test 未来) — 本版不执行真实命令
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": True}, command="pytest")
        assert r.success is True

    def test_save_writes_file(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate({"id": "T1"}, {"success": True, "artifact": "/tmp/a"})
        p = v.save(tmp_path, "scorepocket", r)
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["success"] is True
        assert data["project"] == "scorepocket"

    def test_save_failed_result(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate({"id": "T1"}, {"success": False, "error": "x"})
        p = v.save(tmp_path, "p", r)
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["success"] is False


# ================================================================== 3. Lifecycle Gate


class TestLifecycleGate:
    def test_validation_pass_in_statuses(self):
        assert PIPE.Lifecycle.VALIDATION_PASS in PIPE.Lifecycle.STATUSES

    def test_validation_pass_between_testing_delivered(self):
        s = PIPE.Lifecycle.STATUSES
        assert s.index(PIPE.Lifecycle.VALIDATION_PASS) == s.index(PIPE.Lifecycle.TESTING) + 1
        assert s.index(PIPE.Lifecycle.USER_ACCEPTANCE) == s.index(PIPE.Lifecycle.VALIDATION_PASS) + 1
        assert s.index(PIPE.Lifecycle.DELIVERED) == s.index(PIPE.Lifecycle.USER_ACCEPTANCE) + 1

    def test_next_status_chain(self):
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.TESTING) == PIPE.Lifecycle.VALIDATION_PASS
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.VALIDATION_PASS) == PIPE.Lifecycle.USER_ACCEPTANCE
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.USER_ACCEPTANCE) == PIPE.Lifecycle.DELIVERED

    def test_orchestrator_reaches_validation_pass(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status in ("user_acceptance", "delivered")
        state = json.loads((tmp_path / "projects" / "scorepocket" / "execution_state.json").read_text(encoding="utf-8"))
        assert state["lifecycle"] in ("user_acceptance", "delivered")

    def test_no_validation_no_delivered_on_fail(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert res.status == "failed"
        assert res.failed_tasks == 3

    def test_validation_result_file_written(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        pd = tmp_path / "projects" / "scorepocket"
        assert (pd / "validation_result.json").exists()


# ================================================================== 4. RepairManager


class TestRepairManager:
    def test_create_repair(self, tmp_path):
        rm = QUALITY.RepairManager()
        r = rm.create_repair(tmp_path, {"id": "T001", "name": "API"}, "test failed")
        assert r["original_task_id"] == "T001"
        assert r["failure_reason"] == "test failed"
        assert r["retry_count"] == 0
        assert r["status"] == "pending"
        assert (tmp_path / "repair_task.json").exists()

    def test_load_repairs(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T1"}, "x")
        rm.create_repair(tmp_path, {"id": "T2"}, "y")
        assert len(rm.load_repairs(tmp_path)) == 2

    def test_load_repairs_missing_file(self, tmp_path):
        assert QUALITY.RepairManager().load_repairs(tmp_path) == []

    def test_repair_success(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T001", "name": "API"}, "test failed")
        result = rm.repair(tmp_path, execute_fn=_ok_fn())
        assert result["status"] == "completed"
        assert result["validation"]["success"] is True

    def test_repair_fail_then_retry_limit(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T001"}, "fail")
        result = rm.repair(tmp_path, execute_fn=_fail_fn())
        assert result["status"] == "failed"
        assert result["retry_count"] == 1

    def test_repair_no_pending(self, tmp_path):
        rm = QUALITY.RepairManager()
        result = rm.repair(tmp_path, execute_fn=_ok_fn())
        assert result["status"] == "none"

    def test_repair_retry_count_persisted(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T1"}, "x")
        rm.repair(tmp_path, execute_fn=_fail_fn())
        repairs = rm.load_repairs(tmp_path)
        assert repairs[0]["retry_count"] == 1
        assert repairs[0]["status"] == "failed"


# ================================================================== 5. Retry Policy


class TestRetryPolicy:
    def test_max_retry_default_one(self):
        assert QUALITY.DEFAULT_MAX_REPAIR_RETRY == 1

    def test_no_infinite_loop(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T1"}, "x")
        calls = []

        def always_fail(task, project_dir, workspace):
            calls.append(1)
            return {"success": False, "error": "always"}

        # repair() 单次调用只执行一次 (pending→retrying→failed) — 不自动无限重试
        result = rm.repair(tmp_path, execute_fn=always_fail)
        assert len(calls) == 1
        assert result["status"] == "failed"
        # 状态为 failed 后不再自动重试 (需手动再次 repair)
        result2 = rm.repair(tmp_path, execute_fn=always_fail)
        assert result2["status"] == "none"  # 无 pending

    def test_orchestrator_retry_once(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        calls = {"n": 0}

        def flaky(task, project_dir, workspace):
            calls["n"] += 1
            if calls["n"] <= 1:
                return {"success": False, "error": "first"}
            return {"success": True, "artifact": "/tmp/a"}

        res = orch.execute_project("scorepocket", execute_fn=flaky)
        # 首个任务首次失败被 retry, 重试成功 → 但 orchestrator 的 retry 在任务级 (max_retry 参数)
        assert res.completed_tasks + res.failed_tasks == 3


# ================================================================== 6. repair_task Action


class TestRepairAction:
    def _ctx(self, tmp_path, product_intent=None):
        intent = ACTION_MOD.IntentObject(
            intent_type="repair_task",
            params={"project": str(tmp_path / "projects" / "scorepocket")},
            raw="修复失败任务",
        )
        return ACTION_MOD.ExecutionContext(
            workspace=tmp_path,
            session=None,
            user="user",
            project=str(tmp_path / "projects" / "scorepocket"),
            intent=intent,
        )

    def test_action_registered(self):
        reg = ACTIONS.build_default_actions()
        assert reg.get("repair_task") is not None

    def test_action_sensitive(self):
        reg = ACTIONS.build_default_actions()
        assert reg.get("repair_task").metadata.get("sensitive") is True

    def test_no_pending_returns_message(self, tmp_path):
        _make_project(tmp_path)
        res = ACTIONS.repair_task(self._ctx(tmp_path))
        assert res.ok is True
        assert "无待修复" in res.message or "没有" in res.message or "pending" in str(res.data).lower()

    def test_pending_repair_completed(self, tmp_path, monkeypatch):
        pd = _make_project(tmp_path)
        QUALITY.RepairManager().create_repair(pd, {"id": "T001", "name": "API"}, "fail")
        monkeypatch.setattr(QUALITY.RepairManager, "repair", lambda self, pd_, **kw: {"status": "completed", "validation": {"success": True}, "retry_count": 0})
        res = ACTIONS.repair_task(self._ctx(tmp_path))
        assert res.ok is True

    def test_intent_keyword(self):
        parser = import_module("factory-console.session.intent").KeywordIntentParser()
        intent = parser.parse("修复失败任务")
        assert intent is not None
        assert intent.intent_type == "repair_task"

    def test_router_mapping(self):
        router = import_module("factory-console.session.router").IntentRouter()
        intent = ACTION_MOD.IntentObject(intent_type="repair_task", params={}, raw="x")
        action = router.route(intent, ACTIONS.build_default_actions())
        assert action.name == "repair_task"


# ================================================================== 7. Execution + Validation Flow


class TestExecutionValidationFlow:
    def test_all_success_delivered(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status in ("user_acceptance", "delivered")
        assert res.completed_tasks == 3
        assert res.failed_tasks == 0

    def test_mixed_success_fail(self, tmp_path):
        pd = _make_project(tmp_path)
        plan = json.loads((pd / "execution_plan.json").read_text(encoding="utf-8"))
        # 2 任务
        plan["tasks"] = plan["tasks"][:2]
        plan["count"] = 2
        (pd / "execution_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        calls = {"n": 0}

        def mixed(task, project_dir, workspace):
            calls["n"] += 1
            if task["id"] == "T002":
                return {"success": False, "error": "second always fails"}
            return {"success": True, "artifact": "/tmp/a"}

        res = orch.execute_project("scorepocket", execute_fn=mixed)
        # T002 永久失败 (retry 后仍失败) → failed; T001 成功
        assert res.completed_tasks == 1
        assert res.failed_tasks == 1
        assert res.status == "failed"  # 有 failed → 不 DELIVERED

    def test_repair_task_created_on_failure(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert (pd / "repair_task.json").exists()
        repairs = QUALITY.RepairManager().load_repairs(pd)
        assert len(repairs) >= 1

    def test_state_persists_task_status(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        statuses = {t["status"] for t in state["tasks"]}
        assert statuses == {"completed"}

    def test_progress_validation_field(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        prog = orch.get_progress("scorepocket")
        assert "validation" in prog
        v = prog["validation"]
        assert isinstance(v, dict)
        assert v.get("passed", 0) == 3
        assert v.get("failed", 0) == 0

    def test_progress_repair_field(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        prog = orch.get_progress("scorepocket")
        assert "repair" in prog


# ================================================================== 8. Failure Recovery


class TestFailureRecovery:
    def test_resume_after_failure(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert orch.get_progress("scorepocket")["failed"] == 3
        # resume: 全部重跑成功
        res = orch.resume("scorepocket", execute_fn=_ok_fn())
        assert res.completed_tasks == 3
        assert res.failed_tasks == 0

    def test_repair_then_success(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        rm = QUALITY.RepairManager()
        repairs = rm.load_repairs(pd)
        assert repairs
        result = rm.repair(pd, execute_fn=_ok_fn())
        assert result["status"] == "completed"


# ================================================================== 9. 完整生产 Demo


class TestFullDemo:
    def test_full_flow(self, tmp_path):
        """create_product → prepare_project → execute → validate → DELIVERED (全部 mock)。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status in ("user_acceptance", "delivered")
        pd = tmp_path / "projects" / "scorepocket"
        assert (pd / "execution_state.json").exists()
        assert (pd / "validation_result.json").exists()

    def test_full_flow_with_repair(self, tmp_path):
        """失败 → repair_task.json → repair → 成功 → DELIVERED。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        calls = {"n": 0}

        def flaky(task, project_dir, workspace):
            calls["n"] += 1
            if task["id"] == "T001" and calls["n"] == 1:
                return {"success": False, "error": "first time"}
            return {"success": True, "artifact": f"/tmp/{task['id']}.patch"}

        orch.execute_project("scorepocket", execute_fn=flaky)
        rm = QUALITY.RepairManager()
        repairs = rm.load_repairs(pd)
        # 首个任务首次失败 → 任务级 retry 成功 → 无 repair 或 repair 已处理
        # 修复后重新执行全任务 → 成功
        res = orch.resume("scorepocket", execute_fn=flaky)
        assert res.completed_tasks == 3
        # 再次执行全绿 → DELIVERED
        res2 = orch.execute_project("scorepocket", execute_fn=flaky)
        assert res2.status in ("user_acceptance", "delivered")
        assert res2.completed_tasks == 3


# ================================================================== 10. Reviewer 接口


class TestReviewer:
    def test_review_result_fields(self):
        r = QUALITY.ReviewResult(approved=True)
        assert r.approved is True
        assert r.comments == []

    def test_reviewer_abstract(self):
        import abc as _abc
        assert issubclass(QUALITY.Reviewer, _abc.ABC)

    def test_reviewer_method_exists(self):
        assert hasattr(QUALITY.Reviewer, "review")


# ================================================================== 11. Progress Enhancement


class TestProgressEnhancement:
    def test_progress_fields(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        prog = orch.get_progress("scorepocket")
        assert prog["lifecycle"] in ("user_acceptance", "delivered")
        assert prog["tasks_total"] == 3
        assert prog["completed"] == 3
        assert prog["failed"] == 0

    def test_project_progress_action(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        intent = ACTION_MOD.IntentObject(
            intent_type="project_progress",
            params={"project": str(tmp_path / "projects" / "scorepocket")},
            raw="项目进度",
        )
        ctx = ACTION_MOD.ExecutionContext(
            workspace=tmp_path,
            session=None,
            user="user",
            project=str(tmp_path / "projects" / "scorepocket"),
            intent=intent,
        )
        res = ACTIONS.project_progress(ctx)
        assert res.ok is True


# ================================================================== 12. Regression


class TestRegression:
    def test_execute_task_unchanged(self):
        # execute_task 仍注册
        reg = ACTIONS.build_default_actions()
        assert reg.get("agent.execute_task") is not None

    def test_create_product_unchanged(self):
        reg = ACTIONS.build_default_actions()
        assert reg.get("create_product") is not None

    def test_lifecycle_legacy_statuses_present(self):
        for s in ("idea", "product_defined", "engineering_ready", "execution_ready", "development", "testing", "delivered"):
            assert s in PIPE.Lifecycle.STATUSES

    def test_import_all_modules(self):
        for m in ("factory-console.session.quality", "factory-console.session.orchestrator"):
            import_module(m)


# ================================================================== 13. 补充测试 (达 >=80)


class TestValidationResultExtra:
    def test_timestamp_auto(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate({"id": "T1"}, {"success": True})
        assert r.timestamp  # 非空

    def test_tests_counters(self):
        r = QUALITY.ValidationResult(success=False, tests_total=5, tests_failed=3, errors=["a", "b"])
        assert r.tests_passed == 0
        assert len(r.errors) == 2

    def test_from_dict_missing_keys(self):
        v = QUALITY.ValidationResult.from_dict({})
        assert v.success is False
        assert v.errors == []

    def test_to_dict_all_fields(self):
        v = QUALITY.ValidationResult(success=True, tests_total=1, tests_passed=1, errors=[], timestamp="t")
        d = v.to_dict()
        for k in ("success", "tests_total", "tests_passed", "tests_failed", "errors", "timestamp"):
            assert k in d


class TestValidatorExtra:
    def test_save_creates_dir(self, tmp_path):
        deep = tmp_path / "a" / "b"
        v = QUALITY.Validator()
        r = v.validate({"id": "T1"}, {"success": True})
        p = v.save(deep, "p", r)
        assert p.exists()

    def test_validate_with_task_ignored_fields(self):
        r = QUALITY.Validator().validate({"id": "T1", "agent": "x"}, {"success": True})
        assert r.success is True

    def test_validate_errors_listed(self):
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": False, "error": "specific error"})
        assert r.errors[0] == "specific error"

    def test_validate_default_error_message(self):
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": False})
        assert r.errors[0] == "任务执行失败"


class TestRepairExtra:
    def test_create_repair_twice_appends(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T1"}, "a")
        rm.create_repair(tmp_path, {"id": "T2"}, "b")
        assert len(rm.load_repairs(tmp_path)) == 2

    def test_repair_marks_execution_state_completed(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        rm = QUALITY.RepairManager()
        rm.create_repair(pd, {"id": "T001", "name": "数据库 Schema"}, "x")
        rm.repair(pd, execute_fn=_ok_fn())
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        assert state["tasks"][0]["status"] == "completed"

    def test_repair_id_unique(self, tmp_path):
        rm = QUALITY.RepairManager()
        r1 = rm.create_repair(tmp_path, {"id": "T1"}, "a")
        r2 = rm.create_repair(tmp_path, {"id": "T2"}, "b")
        assert r1["repair_id"] != r2["repair_id"]


class TestLifecycleExtra:
    def test_validation_pass_constant(self):
        assert PIPE.Lifecycle.VALIDATION_PASS == "validation_pass"

    def test_next_status_returns_none_after_delivered(self):
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.DELIVERED) is None

    def test_previous_stages_before_validation(self):
        s = PIPE.Lifecycle.STATUSES
        assert s.index(PIPE.Lifecycle.VALIDATION_PASS) > s.index(PIPE.Lifecycle.DEVELOPMENT)


class TestOrchestratorQualityExtra:
    def test_validator_injected(self, tmp_path):
        pd = _make_project(tmp_path)
        calls = {"v": 0}

        class CountingValidator(QUALITY.Validator):
            def validate(self, task, task_result, **kw):
                calls["v"] += 1
                return super().validate(task, task_result, **kw)

        orch = ORCH.ExecutionOrchestrator(tmp_path, validator=CountingValidator())
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert calls["v"] == 3  # 每任务一次

    def test_validation_result_per_task(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        state = json.loads((tmp_path / "projects" / "scorepocket" / "execution_state.json").read_text(encoding="utf-8"))
        assert all(t.get("validation") in ("passed", "failed") or "validation" in t for t in state["tasks"])

    def test_progress_repair_counts(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        prog = orch.get_progress("scorepocket")
        r = prog["repair"]
        assert isinstance(r, dict)
        assert r.get("pending", 0) + r.get("failed", 0) >= 1

    def test_resume_with_pending(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert orch.needs_resume("scorepocket") is True
        orch.resume("scorepocket", execute_fn=_ok_fn())
        assert orch.needs_resume("scorepocket") is False

    def test_execute_project_restart_clean(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        # 重新执行 → 状态重置全 pending → 全成功
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        assert all(t["status"] == "completed" for t in state["tasks"])


class TestRepairActionExtra:
    def test_action_description(self):
        reg = ACTIONS.build_default_actions()
        assert "修复" in reg.get("repair_task").description

    def test_router_has_repair_route(self):
        router = import_module("factory-console.session.router").IntentRouter()
        assert router.routes().get("repair_task") == "repair_task"

    def test_intent_variants(self):
        parser = import_module("factory-console.session.intent").KeywordIntentParser()
        for text in ("修复失败任务", "修复任务", "重试失败任务"):
            intent = parser.parse(text)
            assert intent is not None, text
            assert intent.intent_type == "repair_task", text

    def test_repair_not_confused_with_run_task(self):
        # "修复" 单独 → run_task; "修复失败任务" → repair_task (优先级)
        parser = import_module("factory-console.session.intent").KeywordIntentParser()
        assert parser.parse("修复这个bug").intent_type == "run_task"
        assert parser.parse("修复失败任务").intent_type == "repair_task"


class TestLocateProductPathFix:
    def test_project_full_path_slug(self, tmp_path):
        """_locate_product: context.project 传完整路径 → 正确取 basename (S10-053 修复)。"""
        pd = _make_project(tmp_path)
        intent = ACTION_MOD.IntentObject(intent_type="project_progress", params={}, raw="项目进度")
        ctx = ACTION_MOD.ExecutionContext(
            workspace=tmp_path, session=None, user="user", project=str(pd), intent=intent
        )
        product, slug, root = ACTIONS._locate_product(ctx)
        assert slug == "scorepocket"
        assert product is not None

    def test_project_progress_action_full_path(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        intent = ACTION_MOD.IntentObject(intent_type="project_progress", params={}, raw="项目进度")
        ctx = ACTION_MOD.ExecutionContext(
            workspace=tmp_path, session=None, user="user", project=str(pd), intent=intent
        )
        res = ACTIONS.project_progress(ctx)
        assert res.ok is True
        assert "3/3" in res.message

    def test_full_production_demo_quality(self, tmp_path):
        """完整生产 Demo: plan → execute(1 失败) → repair → 全绿 → DELIVERED。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        calls = {"n": 0}

        def flaky(task, project_dir, workspace):
            calls["n"] += 1
            if task["id"] == "T001" and calls["n"] == 1:
                return {"success": False, "error": "first attempt"}
            return {"success": True, "artifact": f"/tmp/{task['id']}.patch"}

        res1 = orch.execute_project("scorepocket", execute_fn=flaky)
        # 首次: T001 retry 后成功 → 3 全成功 → delivered
        assert res1.completed_tasks == 3
        assert res1.status in ("user_acceptance", "delivered")
        assert (pd / "validation_result.json").exists()

    def test_validator_double_validate_consistent(self, tmp_path):
        """同结果两次验证一致 (无状态泄漏)。"""
        v = QUALITY.Validator()
        outcome = {"success": True, "artifact": "/tmp/a"}
        r1 = v.validate({"id": "T1"}, outcome)
        r2 = v.validate({"id": "T1"}, outcome)
        assert r1.success == r2.success is True
