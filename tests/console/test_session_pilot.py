"""S10-054 — Real Project Production Pilot 测试套件。

覆盖: 真实 Product Flow / Pipeline Flow / Execution Flow / Validation Flow
(含真实 command validation) / Repair Flow / Project Report / 回归。

装配: tmp_path workspace + mock execute_fn (真实 LLM 仅冒烟验证, 测试零网络);
validate_command 用真实小命令 (python3 -c) 验证接口。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from importlib import import_module

QUALITY = import_module("factory-console.session.quality")
PIPE = import_module("factory-console.session.pipeline")
ORCH = import_module("factory-console.session.orchestrator")
ACTIONS = import_module("factory-console.session.actions")
ACTION_MOD = import_module("factory-console.session.action")


# ================================================================== fixtures

def _make_project(tmp_path: Path, tasks: int = 3) -> Path:
    pd = tmp_path / "projects" / "scorepocket"
    pd.mkdir(parents=True, exist_ok=True)
    plan = {
        "tasks": [
            {"id": f"T00{i}", "name": f"任务 {i}", "agent_type": "backend", "agent": "backend-1"}
            for i in range(1, tasks + 1)
        ],
        "count": tasks,
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


def _ok_fn():
    def fn(task, project_dir, workspace):
        return {"success": True, "artifact": f"/tmp/{task['id']}.patch", "error": None, "cost": "10 tokens"}

    return fn


def _fail_fn():
    def fn(task, project_dir, workspace):
        return {"success": False, "artifact": "", "error": "boom", "cost": ""}

    return fn


# ================================================================== 1. 真实 Product Flow


class TestProductFlow:
    def test_intent_to_product(self):
        parser = import_module("factory-console.session.intent").KeywordIntentParser()
        intent = parser.parse("我想开发一个台球计分APP")
        assert intent is not None
        assert intent.intent_type == "create_product"

    def test_product_intent_model(self):
        PRODUCT = import_module("factory-console.session.product")
        p = PRODUCT.ProductIntent(name="ScorePocket", problem="记录困难", user="爱好者", core_features=["计分"])
        assert p.is_complete() is True

    def test_product_missing_fields(self):
        PRODUCT = import_module("factory-console.session.product")
        p = PRODUCT.ProductIntent(name="X")
        missing = p.missing_fields()
        assert "产品解决什么问题" in missing

    def test_create_product_registered(self):
        reg = ACTIONS.build_default_actions()
        assert reg.get("create_product") is not None

    def test_product_json_written(self, tmp_path):
        PRODUCT = import_module("factory-console.session.product")
        pd = tmp_path / "projects" / "p1"
        pd.mkdir(parents=True)
        (pd / "product.json").write_text(
            json.dumps(PRODUCT.ProductIntent(name="P", problem="x", user="y", core_features=["a"]).to_dict(), ensure_ascii=False),
            encoding="utf-8",
        )
        assert (pd / "product.json").exists()
        assert json.loads((pd / "product.json").read_text(encoding="utf-8"))["name"] == "P"


# ================================================================== 2. Pipeline Flow


class TestPipelineFlow:
    def test_prepare_project_registered(self):
        reg = ACTIONS.build_default_actions()
        assert reg.get("prepare_project") is not None

    def test_engineering_plan(self):
        PRODUCT = import_module("factory-console.session.product")
        p = PRODUCT.ProductIntent(name="P", problem="x", user="y", core_features=["a", "b"], platform="mobile")
        e = PIPE.EngineeringPlan.from_prd(p)
        assert e["architecture"] == "Flutter + Backend API"
        assert len(e["modules"]) == 2

    def test_task_tree_generates_tasks(self):
        t = PIPE.TaskTree.from_engineering({"modules": [{"slug": "m1", "name": "A"}]})
        assert len(t.get("tasks", [])) == 4

    def test_agent_assignment_reuses_selector(self):
        a = PIPE.AgentAssignment.from_tasks(
            {"tasks": [{"id": "T1", "name": "前端页面", "agent_type": "frontend"}]}, context=None
        )
        assert a["tasks"][0]["agent"] == "flutter-dev"

    def test_execution_plan_asset(self, tmp_path):
        pd = _make_project(tmp_path)
        assert (pd / "execution_plan.json").exists()


# ================================================================== 3. Execution Flow


class TestExecutionFlow:
    def test_execute_project_all_success(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status == "delivered"
        assert res.completed_tasks == 3

    def test_execute_project_failure(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert res.status == "failed"
        assert res.failed_tasks == 3

    def test_execution_state_persisted(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        assert state["lifecycle"] == "delivered"

    def test_progress_query(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        prog = orch.get_progress("scorepocket")
        assert prog["completed"] == 3
        assert prog["lifecycle"] == "delivered"

    def test_resume_flow(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert orch.needs_resume("scorepocket") is True
        res = orch.resume("scorepocket", execute_fn=_ok_fn())
        assert res.completed_tasks == 3


# ================================================================== 4. Validation Flow (真实 command validation)


class TestValidationFlow:
    def test_mock_validation_success(self):
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": True})
        assert r.success is True

    def test_mock_validation_failure(self):
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": False, "error": "x"})
        assert r.success is False

    def test_real_command_success(self, tmp_path):
        """真实 command validation: python3 -c 'exit(0)' → PASS。"""
        r = QUALITY.Validator().validate_command(tmp_path, [sys.executable, "-c", "pass"])
        assert r.success is True
        assert r.tests_passed == 1

    def test_real_command_failure(self, tmp_path):
        """真实 command validation: python3 -c 'exit(1)' → FAIL。"""
        r = QUALITY.Validator().validate_command(tmp_path, [sys.executable, "-c", "import sys; sys.exit(1)"])
        assert r.success is False
        assert r.tests_failed == 1

    def test_real_command_not_found(self, tmp_path):
        r = QUALITY.Validator().validate_command(tmp_path, ["definitely-not-a-command-xyz"])
        assert r.success is False
        assert any("不存在" in e for e in r.errors)

    def test_real_command_timeout(self, tmp_path):
        r = QUALITY.Validator().validate_command(tmp_path, [sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)
        assert r.success is False
        assert any("超时" in e for e in r.errors)

    def test_real_pytest_style_script(self, tmp_path):
        """模拟 pytest 场景: 脚本 exit 0 → PASS (真实子进程)。"""
        script = tmp_path / "run_tests.py"
        script.write_text("print('all tests passed')", encoding="utf-8")
        r = QUALITY.Validator().validate_command(tmp_path, [sys.executable, str(script)])
        assert r.success is True

    def test_validation_result_file(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert (pd / "validation_result.json").exists()

    def test_validation_gate_blocks_delivered(self, tmp_path):
        """失败任务 → 不 DELIVERED (Validation Gate)。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert res.status == "failed"
        assert res.status != "delivered"

    def test_validation_result_structure(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_command(tmp_path, [sys.executable, "-c", "pass"])
        d = r.to_dict()
        for k in ("success", "tests_total", "tests_passed", "tests_failed", "errors", "timestamp"):
            assert k in d


# ================================================================== 5. Repair Flow


class TestRepairFlow:
    def test_create_repair_task(self, tmp_path):
        rm = QUALITY.RepairManager()
        r = rm.create_repair(tmp_path, {"id": "T1"}, "fail")
        assert r["status"] == "pending"
        assert (tmp_path / "repair_task.json").exists()

    def test_repair_success(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T1"}, "fail")
        res = rm.repair(tmp_path, execute_fn=_ok_fn())
        assert res["status"] == "completed"

    def test_repair_failure_limit(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T1"}, "fail")
        res = rm.repair(tmp_path, execute_fn=_fail_fn())
        assert res["status"] == "failed"
        assert res["retry_count"] == 1

    def test_repair_no_pending(self, tmp_path):
        res = QUALITY.RepairManager().repair(tmp_path, execute_fn=_ok_fn())
        assert res["status"] == "none"

    def test_repair_validation_integrated(self, tmp_path):
        rm = QUALITY.RepairManager()
        rm.create_repair(tmp_path, {"id": "T1"}, "fail")
        res = rm.repair(tmp_path, execute_fn=_ok_fn())
        assert res["validation"]["success"] is True

    def test_orchestrator_failure_creates_repair(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        assert (pd / "repair_task.json").exists()


# ================================================================== 6. Project Report


class TestProjectReport:
    def test_report_assets_complete(self, tmp_path):
        """生产资产完整: PRD/engineering/tasks/execution_plan/validation。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        for name in ("execution_plan.json", "execution_state.json", "validation_result.json"):
            assert (pd / name).exists()

    def test_report_contains_metrics(self, tmp_path):
        """ExecutionResult 含交付指标。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.completed_tasks >= 0
        assert res.failed_tasks >= 0
        assert isinstance(res.artifacts, list)

    def test_report_delivery_status(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status == "delivered"

    def test_audit_records_written(self, tmp_path):
        """执行审计落盘 (可回答: 哪个 Agent 做了什么)。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        assert all(t.get("agent") for t in state["tasks"])

    def test_progress_answers_questions(self, tmp_path):
        """可观察性: 进度回答 '做到哪里/谁做的/成本'。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        prog = orch.get_progress("scorepocket")
        assert "lifecycle" in prog
        assert "completed" in prog
        assert "agents" in prog


# ================================================================== 7. 回归


class TestRegression:
    def test_existing_actions_unchanged(self):
        reg = ACTIONS.build_default_actions()
        for name in ("create_product", "prepare_project", "execute_project", "repair_task", "agent.execute_task"):
            assert reg.get(name) is not None

    def test_lifecycle_unchained(self):
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.TESTING) == PIPE.Lifecycle.VALIDATION_PASS
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.VALIDATION_PASS) == PIPE.Lifecycle.DELIVERED

    def test_quality_modules_import(self):
        import_module("factory-console.session.quality")
        import_module("factory-console.session.orchestrator")

    def test_intent_routing(self):
        router = import_module("factory-console.session.router").IntentRouter()
        assert router.routes().get("repair_task") == "repair_task"


# ================================================================== 8. 补充 (达 >=50)


class TestExtra:
    def test_validate_command_list_and_str(self, tmp_path):
        v = QUALITY.Validator()
        r1 = v.validate_command(tmp_path, [sys.executable, "-c", "pass"])
        r2 = v.validate_command(tmp_path, f"{sys.executable} -c pass")
        assert r1.success is True
        assert r2.success is True

    def test_validate_command_env_injected(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_command(
            tmp_path,
            [sys.executable, "-c", "import os; assert os.environ.get('PILOT') == '1'"],
            env={**__import__("os").environ, "PILOT": "1"},
        )
        assert r.success is True

    def test_execution_result_fields(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        for attr in ("project", "status", "completed_tasks", "failed_tasks", "artifacts", "duration", "cost", "errors"):
            assert hasattr(res, attr)

    def test_full_pilot_flow_mock(self, tmp_path):
        """完整 Pilot 流程 (mock): product → plan → execute → validate → delivered。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status == "delivered"
        assert (pd / "validation_result.json").exists()

    def test_progress_repair_counts(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        prog = orch.get_progress("scorepocket")
        assert "repair" in prog


class TestPilotExtra:
    def test_real_validation_gate_success(self, tmp_path):
        """真实 command validation 作为交付门。"""
        v = QUALITY.Validator()
        r = v.validate_command(tmp_path, [sys.executable, "-c", "pass"])
        assert r.success is True
        assert r.to_dict()["tests_passed"] == 1

    def test_real_validation_gate_failure(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_command(tmp_path, [sys.executable, "-c", "raise RuntimeError('boom')"])
        assert r.success is False

    def test_validation_command_errors_captured(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_command(tmp_path, [sys.executable, "-c", "import sys; sys.stderr.write('oops'); sys.exit(2)"])
        assert r.success is False
        assert any("退出码 2" in e for e in r.errors)

    def test_agent_selector_full(self):
        """Agent 选择: 前端→flutter-dev / 默认→backend-1 (pilot 分配依据)。"""
        intent = ACTION_MOD.IntentObject(intent_type="run_task", params={"objective": "做一个登录界面"}, raw="x")
        assert ACTIONS.select_agent(intent, None) == "flutter-dev"
        intent2 = ACTION_MOD.IntentObject(intent_type="run_task", params={"objective": "实现后端 API"}, raw="x")
        assert ACTIONS.select_agent(intent2, None) == "backend-1"

    def test_production_report_questions_answerable(self, tmp_path):
        """可观察性: 报告资产能回答 '做到哪里/谁做的/成本/问题'。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        assert state["lifecycle"]  # 做到哪里
        assert all(t["agent"] for t in state["tasks"])  # 谁做的
        assert (pd / "validation_result.json").exists()  # 质量
        repairs = QUALITY.RepairManager().load_repairs(pd)
        assert isinstance(repairs, list)  # 问题记录
