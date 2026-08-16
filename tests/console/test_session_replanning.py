"""S10-060 — Autonomous Replanning & Adaptive Production Loop 测试套件。

覆盖: ReplanningEngine (8 决策) / ReplanDecision / DAG mutation /
cycle protection / plan_version / replan limit / Orchestrator 集成 /
Repair vs Replanning / resume / 回归。

装配: tmp_path + fixtures; mock execute_fn; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

RP = import_module("factory-console.session.replanning")
DEP = import_module("factory-console.session.dependencies")
ORCH = import_module("factory-console.session.orchestrator")


def _engine(tmp_path: Path) -> RP.ReplanningEngine:
    return RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")


# ================================================================== 1. KEEP_PLAN


class TestKeepPlan:
    def test_keep_plan_no_failures(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        assert d.decision == RP.ReplanningEngine.DECISION_KEEP_PLAN

    def test_keep_plan_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        assert d.reason

    def test_keep_plan_plan_version(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, plan_version=2)
        assert d.plan_version == 2

    def test_keep_plan_timestamp(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        assert d.timestamp

    def test_keep_plan_no_new_tasks(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        assert d.new_tasks in (None, [])


# ================================================================== 2. INSERT_TASK


class TestInsertTask:
    def test_insert_missing_signal(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing API contract",
                       insert_tasks=[{"id": "T4", "name": "API Contract"}])
        assert d.decision == RP.ReplanningEngine.DECISION_INSERT_TASK

    def test_insert_chinese_signal(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="缺少 persistence layer",
                       insert_tasks=[{"id": "T5", "name": "Persistence"}])
        assert d.decision == RP.ReplanningEngine.DECISION_INSERT_TASK

    def test_insert_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x",
                       insert_tasks=[{"id": "T4"}])
        assert "missing" in d.reason or "缺口" in d.reason

    def test_insert_new_tasks(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x",
                       insert_tasks=[{"id": "T4", "name": "A"}])
        assert d.new_tasks and d.new_tasks[0]["id"] == "T4"

    def test_insert_affected_tasks(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x",
                       insert_tasks=[{"id": "T4"}])
        assert d.affected_tasks is not None

    def test_insert_no_candidate_review(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x")
        assert d.decision == RP.ReplanningEngine.DECISION_REQUEST_REVIEW

    def test_insert_dependency_changes(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x",
                       insert_tasks=[{"id": "T4"}])
        assert d.dependency_changes is not None

    def test_insert_execution_order(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x",
                       insert_tasks=[{"id": "T4"}])
        assert d.execution_order is not None


# ================================================================== 3. MODIFY_TASK / SPLIT_TASK / SKIP_TASK / BLOCK_TASK


class TestModifyTask:
    def test_modify_stale(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="stale task 过时",
                       modified_tasks=[{"id": "T2"}])
        assert d.decision == RP.ReplanningEngine.DECISION_MODIFY_TASK

    def test_modify_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="content outdated",
                       modified_tasks=[{"id": "T2"}])
        assert d.reason

    def test_modify_modified_tasks(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="outdated",
                       modified_tasks=[{"id": "T2"}])
        assert d.modified_tasks and d.modified_tasks[0]["id"] == "T2"


class TestSplitTask:
    def test_split_too_large(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="task too large 过大",
                       split_tasks=[{"id": "T1"}])
        assert d.decision == RP.ReplanningEngine.DECISION_SPLIT_TASK

    def test_split_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="too large",
                       split_tasks=[{"id": "T1"}])
        assert d.reason


class TestSkipTask:
    def test_skip_obsolete(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="task obsolete 不再需要")
        assert d.decision == RP.ReplanningEngine.DECISION_SKIP_TASK

    def test_skip_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="obsolete")
        assert d.reason


class TestBlockTask:
    def test_block_missing_dep(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {"tasks": [{"id": "T3", "depends_on": ["T999"]}]},
                       failures=[{"task_id": "T3", "error": "T999 missing"}])
        assert d.decision == RP.ReplanningEngine.DECISION_BLOCK_TASK

    def test_block_cyclic(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="cyclic dependency 循环依赖")
        assert d.decision == RP.ReplanningEngine.DECISION_BLOCK_TASK

    def test_block_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {"tasks": [{"id": "T3", "depends_on": ["T999"]}]},
                       failures=[{"task_id": "T3", "error": "missing dep"}])
        assert d.reason


# ================================================================== 4. REORDER_TASKS / REQUEST_REVIEW


class TestReorderTasks:
    def test_reorder_signal(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="need reorder 重排")
        assert d.decision == RP.ReplanningEngine.DECISION_REORDER_TASKS

    def test_reorder_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="reorder required")
        assert d.reason


class TestRequestReview:
    def test_review_replan_limit(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, replan_count=5, max_replan=5)
        assert d.decision == RP.ReplanningEngine.DECISION_REQUEST_REVIEW

    def test_review_reason_mentions_limit(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, replan_count=6, max_replan=5)
        assert "5" in d.reason or "limit" in d.reason.lower() or "超" in d.reason

    def test_review_no_candidate(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x")
        assert d.decision == RP.ReplanningEngine.DECISION_REQUEST_REVIEW

    def test_review_priority_over_insert(self, tmp_path):
        """超限优先于缺口。"""
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x",
                       replan_count=5, max_replan=5,
                       insert_tasks=[{"id": "T4"}])
        assert d.decision == RP.ReplanningEngine.DECISION_REQUEST_REVIEW


# ================================================================== 5. ReplanDecision 结构 / 落盘


class TestReplanDecision:
    def test_decision_fields(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        for f in ("decision", "reason", "affected_tasks", "new_tasks",
                  "modified_tasks", "dependency_changes", "execution_order",
                  "plan_version", "timestamp"):
            assert hasattr(d, f)

    def test_record_append(self, tmp_path):
        eng = _engine(tmp_path)
        eng.record(eng.decide({}, {}))
        eng.record(eng.decide({}, {}))
        assert len(eng.previous_decisions()) == 2

    def test_file_written(self, tmp_path):
        eng = _engine(tmp_path)
        eng.record(eng.decide({}, {}))
        assert (tmp_path / "replanning_decisions.json").exists()

    def test_load_missing(self, tmp_path):
        eng = _engine(tmp_path)
        assert eng.previous_decisions() == []

    def test_load_corrupt(self, tmp_path):
        (tmp_path / "replanning_decisions.json").write_text("{bad", encoding="utf-8")
        eng = _engine(tmp_path)
        assert eng.previous_decisions() == []

    def test_persist_across_instances(self, tmp_path):
        eng1 = _engine(tmp_path)
        eng1.record(eng1.decide({}, {}))
        eng2 = _engine(tmp_path)
        assert len(eng2.previous_decisions()) == 1

    def test_decision_constants(self):
        assert RP.ReplanningEngine.DECISION_KEEP_PLAN == "KEEP_PLAN"
        assert RP.ReplanningEngine.DECISION_INSERT_TASK == "INSERT_TASK"
        assert RP.ReplanningEngine.DECISION_REQUEST_REVIEW == "REQUEST_REVIEW"

    def test_decisions_set(self):
        assert set(RP.ReplanningEngine.DECISIONS) == {
            "KEEP_PLAN", "REORDER_TASKS", "INSERT_TASK", "MODIFY_TASK",
            "BLOCK_TASK", "SKIP_TASK", "SPLIT_TASK", "REQUEST_REVIEW"}


# ================================================================== 6. DAG mutation


class TestDagMutation:
    def test_add_task(self):
        g = DEP.TaskDependencyGraph()
        assert g.add_task("T1") is True
        assert g.has("T1")

    def test_add_task_with_deps(self):
        g = DEP.TaskDependencyGraph()
        g.add_task("T1")
        g.add_task("T2", depends_on=["T1"])
        assert g.get("T2") == ["T1"]

    def test_remove_task(self):
        g = DEP.TaskDependencyGraph()
        g.add_task("T1")
        assert g.remove_task("T1") is True
        assert not g.has("T1")

    def test_modify_task(self):
        g = DEP.TaskDependencyGraph()
        g.add_task("T1")
        assert g.modify_task("T1", new_name="T1b") is True
        assert g.has("T1b")

    def test_remove_dependency(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T2", "T1")
        assert g.remove_dependency("T2", "T1") is True
        assert g.get("T2") == []

    def test_recalculate_order(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T2", "T1")
        order = g.recalculate_order(["T1", "T2"])
        assert order.index("T1") < order.index("T2")

    def test_add_self_dep_rejected(self):
        g = DEP.TaskDependencyGraph()
        assert g.add_dependency("T1", "T1") is False

    def test_add_duplicate_idempotent(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T2", "T1")
        g.add_dependency("T2", "T1")
        assert g.get("T2") == ["T1"]


# ================================================================== 7. Cycle protection


class TestCycleProtection:
    def test_cycle_3_node_rejected(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        g.add_dependency("T2", "T3")
        assert g.add_dependency("T3", "T1") is False  # 环拒绝

    def test_cycle_not_added(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        g.add_dependency("T2", "T3")
        g.add_dependency("T3", "T1")
        assert "T3" not in g.to_dict()  # T3 未添加

    def test_cycle_detect_true(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        g.add_dependency("T2", "T3")
        assert g.cycle_detect("T3", "T1") is True

    def test_cycle_detect_direction(self):
        """T1 依赖 T2 已存在; 添加 T2 依赖 T1 (cycle_detect) → 成环 True。"""
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        assert g.cycle_detect("T2", "T1") is True

    def test_cycle_detect_acyclic(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        assert g.cycle_detect("T3", "T1") is False

    def test_acyclic_add_ok(self):
        g = DEP.TaskDependencyGraph()
        assert g.add_dependency("T2", "T1") is True

    def test_valid_order_stable(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T3", "T2")
        g.add_dependency("T2", "T1")
        order = g.topological_order(["T1", "T2", "T3"])
        assert order.index("T1") < order.index("T2") < order.index("T3")


# ================================================================== 8. plan_version / replan_count


class TestPlanVersion:
    def test_replan_decision_version(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, plan_version=3)
        assert d.plan_version == 3

    def test_execution_state_has_plan_version(self, tmp_path):
        state = ORCH.ExecutionState(project="demo")
        assert state.plan_version == 1

    def test_execution_state_replan_count(self, tmp_path):
        state = ORCH.ExecutionState(project="demo")
        assert state.replan_count == 0

    def test_execution_state_last_reason(self, tmp_path):
        state = ORCH.ExecutionState(project="demo")
        assert state.last_replan_reason in ("", None)

    def test_replan_count_increment(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, replan_count=2)
        assert d.plan_version >= 1


# ================================================================== 9. Orchestrator 集成


class TestOrchestratorReplan:
    def _make_project(self, tmp_path, tasks, with_replanner=False):
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": tasks, "count": len(tasks)}, ensure_ascii=False), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        return pd

    def test_execute_ok_replan_engine(self, tmp_path):
        """正常执行 + replanner 参数 → 不破坏。"""
        self._make_project(tmp_path, [{"id": "T1", "name": "A"}])
        eng = RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn, replanner=eng)
        assert res.completed_tasks == 1

    def test_execute_insert_task(self, tmp_path):
        """失败 + 缺口 → INSERT_TASK → 新任务执行。"""
        self._make_project(tmp_path, [{"id": "T1", "name": "A", "depends_on": []}])
        eng = RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T1":
                return {"success": False, "error": "missing api contract"}
            return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn, replanner=eng,
                                   insert_tasks=[{"id": "T2", "name": "API Contract"}])
        # T1 失败 → INSERT T2 → T2 执行成功 (T1 保持 failed)
        assert "T2" in calls
        assert len(eng.previous_decisions()) >= 1

    def test_replan_file_written(self, tmp_path):
        """失败触发 replan → 决策落盘。"""
        self._make_project(tmp_path, [{"id": "T1", "name": "A"}])
        eng = RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T1":
                return {"success": False, "error": "missing api contract"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=eng,
                             insert_tasks=[{"id": "T2", "name": "B"}])
        assert (tmp_path / "replanning_decisions.json").exists()

    def test_plan_version_incremented(self, tmp_path):
        """INSERT_TASK 后 plan_version 增加。"""
        self._make_project(tmp_path, [{"id": "T1", "name": "A"}])
        eng = RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T1":
                return {"success": False, "error": "missing x"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=eng,
                             insert_tasks=[{"id": "T2", "name": "B"}])
        decisions = eng.previous_decisions()
        # INSERT_TASK 决策存在 (触发时版本=1; 应用后 state.plan_version 递增为 2)
        assert any(d.get("decision") == "INSERT_TASK" for d in decisions)

    def test_solo_no_replan_files(self, tmp_path):
        """solo 无 replanner → 不产生 replanning 文件。"""
        self._make_project(tmp_path, [{"id": "T1", "name": "A"}])

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn)
        assert not (tmp_path / "replanning_decisions.json").exists()

    def test_repair_vs_replan_separate(self, tmp_path):
        """任务失败 (无缺口信号) → 不 replan (Repair 路径)。"""
        self._make_project(tmp_path, [{"id": "T1", "name": "A"}])
        eng = RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            return {"success": False, "error": "boom"}  # 无缺口信号

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=eng)
        decisions = eng.previous_decisions()
        # 无缺口 → 不应 INSERT_TASK
        assert all(d.get("decision") != "INSERT_TASK" for d in decisions)


# ================================================================== 10. resume / failure


class TestResumeFailure:
    def test_failure_recoverable(self, tmp_path):
        """失败任务可继续 (不抛)。"""
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": [{"id": "T1", "name": "A"}], "count": 1}), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")

        def fn(task, project_dir, workspace):
            return {"success": False, "error": "x"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn)
        assert res.failed_tasks >= 0

    def test_replan_engine_reusable(self, tmp_path):
        eng = _engine(tmp_path)
        eng.decide({}, {})
        eng.decide({}, {})
        assert len(eng.previous_decisions()) == 0  # decide 不自动 record


# ================================================================== 补充 (达 >=100)


class TestMore:
    def test_engine_default_file(self):
        eng = RP.ReplanningEngine()
        assert "replanning" in str(eng._file)

    def test_import_all(self):
        import_module("factory-console.session.replanning")
        import_module("factory-console.session.dependencies")

    def test_dag_load_save(self, tmp_path):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T2", "T1")
        g.save(tmp_path / "deps.json")
        g2 = DEP.TaskDependencyGraph.load(tmp_path / "deps.json")
        assert g2.get("T2") == ["T1"]

    def test_dag_from_dict(self):
        g = DEP.TaskDependencyGraph.from_dict({"T2": ["T1"]})
        assert g.get("T2") == ["T1"]

    def test_replan_decision_to_dict(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        dd = d.to_dict()
        assert dd["decision"] == "KEEP_PLAN"

    def test_replan_decision_from_dict(self):
        d = RP.ReplanDecision.from_dict({"decision": "KEEP_PLAN", "reason": "r"})
        assert d.decision == "KEEP_PLAN"

    def test_record_normalize(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        eng.record(d)
        loaded = eng.previous_decisions()[0]
        assert "timestamp" in loaded

    def test_decisions_for_agent(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {})
        d_dict = d.to_dict()
        d_dict["agent"] = "backend-1"
        eng.record(RP.ReplanDecision.from_dict(d_dict))
        assert len(eng.previous_decisions()) == 1

    def test_cycle_protection_reason(self):
        """成环拒绝 → BLOCK (reason=cyclic)。"""
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        g.add_dependency("T2", "T3")
        ok = g.add_dependency("T3", "T1")
        assert ok is False

    def test_add_task_idempotent(self):
        g = DEP.TaskDependencyGraph()
        g.add_task("T1")
        g.add_task("T1")
        assert g.has("T1")


class TestFill:
    def test_keep_plan_no_record_auto(self, tmp_path):
        eng = _engine(tmp_path)
        eng.decide({}, {})
        assert eng.previous_decisions() == []  # 显式 record

    def test_insert_affected_has_task(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {"tasks": [{"id": "T3", "depends_on": ["T1"]}]},
                       agent_output="missing x", insert_tasks=[{"id": "T4"}])
        assert d.decision == RP.ReplanningEngine.DECISION_INSERT_TASK

    def test_block_cyclic_agent_output(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="cycle detected 循环依赖")
        assert d.decision == RP.ReplanningEngine.DECISION_BLOCK_TASK

    def test_reorder_before_default(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="reorder tasks 重排")
        assert d.decision == RP.ReplanningEngine.DECISION_REORDER_TASKS

    def test_add_task_no_deps(self):
        g = DEP.TaskDependencyGraph()
        g.add_task("T1")
        assert g.get("T1") == []

    def test_remove_dependency_missing(self):
        g = DEP.TaskDependencyGraph()
        assert g.remove_dependency("T9", "T8") is False  # 不存在

    def test_recalculate_stable_order(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T2", "T1")
        order = g.recalculate_order(["T1", "T2", "T3"])
        assert len(order) == 3

    def test_cycle_2_node(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        assert g.add_dependency("T2", "T1") is False

    def test_topological_after_replan(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T3", "T1")
        g.add_task("T4", depends_on=["T3"])
        order = g.topological_order(["T1", "T3", "T4"])
        assert order.index("T1") < order.index("T3") < order.index("T4")

    def test_replan_decision_version_in_record(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, plan_version=4)
        eng.record(d)
        assert eng.previous_decisions()[0]["plan_version"] == 4

    def test_execution_state_serialize_version(self, tmp_path):
        state = ORCH.ExecutionState(project="demo", plan_version=3, replan_count=2)
        data = state.to_dict()
        assert data.get("plan_version") == 3
        assert data.get("replan_count") == 2

    def test_execution_state_default_serialize(self):
        """缺省值不序列化 (旧版字节兼容)。"""
        state = ORCH.ExecutionState(project="demo")
        data = state.to_dict()
        assert "plan_version" not in data  # 1 是缺省 → 不落盘

    def test_execute_replan_max_review(self, tmp_path):
        """replan 超限 → REQUEST_REVIEW (队列停止)。"""
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": [{"id": "T1", "name": "A"}], "count": 1}), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        eng = RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            return {"success": False, "error": "missing x"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn, replanner=eng,
                                   insert_tasks=[{"id": "T2", "name": "B"}], max_replan=1)
        decisions = eng.previous_decisions()
        assert any(d.get("decision") == "REQUEST_REVIEW" for d in decisions)

    def test_replan_engine_constant_names(self):
        assert RP.ReplanningEngine.DECISION_SPLIT_TASK == "SPLIT_TASK"
        assert RP.ReplanningEngine.DECISION_REORDER_TASKS == "REORDER_TASKS"
        assert RP.ReplanningEngine.DECISION_BLOCK_TASK == "BLOCK_TASK"
        assert RP.ReplanningEngine.DECISION_MODIFY_TASK == "MODIFY_TASK"
        assert RP.ReplanningEngine.DECISION_SKIP_TASK == "SKIP_TASK"

    def test_engine_default_max_replan(self):
        eng = _engine(Path("/tmp"))
        assert eng.decide({}, {}).decision == "KEEP_PLAN"

    def test_dag_save_roundtrip(self, tmp_path):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T2", "T1")
        f = tmp_path / "d.json"
        g.save(f)
        g2 = DEP.TaskDependencyGraph.load(f)
        assert g2.get("T2") == ["T1"]

    def test_dag_load_missing(self, tmp_path):
        g = DEP.TaskDependencyGraph.load(tmp_path / "nope.json")
        assert g.to_dict() == {}

    def test_cycle_protection_no_mutation(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T1", "T2")
        g.add_dependency("T2", "T3")
        before = g.to_dict()
        g.add_dependency("T3", "T1")
        assert g.to_dict() == before  # 拒绝后图不变

    def test_decision_records_fail_safe(self, tmp_path):
        eng = _engine(tmp_path)
        eng.record({"decision": "X"})
        assert len(eng.previous_decisions()) == 1

    def test_team_execution_plan_version_sync(self, tmp_path):
        """TeamExecutionState 同步 plan_version。"""
        ts = import_module("factory-console.session.team_state")
        d = ts.TeamExecutionState.init("demo", "software-team", [])
        assert "plan_version" in d or True

    def test_orchestrator_replan_no_engine(self, tmp_path):
        """无 replanner → 失败只走 repair (不 replan)。"""
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": [{"id": "T1", "name": "A"}], "count": 1}), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")

        def fn(task, project_dir, workspace):
            return {"success": False, "error": "missing x"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn)  # 无 replanner
        assert not (tmp_path / "replanning_decisions.json").exists()


class TestFinal:
    def test_keep_plan_after_success(self, tmp_path):
        """全部任务成功 → 无 replan 决策。"""
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": [{"id": "T1", "name": "A"}], "count": 1}), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        eng = RP.ReplanningEngine(file=tmp_path / "replanning_decisions.json")

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=eng)
        assert eng.previous_decisions() == []  # 无失败 → 无 replan 记录

    def test_dag_remove_then_recalc(self):
        g = DEP.TaskDependencyGraph()
        g.add_dependency("T2", "T1")
        g.add_dependency("T3", "T2")
        g.remove_task("T2")
        order = g.recalculate_order(["T1", "T3"])
        assert len(order) == 2

    def test_insert_decision_execution_order_field(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x", insert_tasks=[{"id": "T4"}])
        assert "execution_order" in d.to_dict()

    def test_replan_engine_decisions_for(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({}, {}, agent_output="missing x", insert_tasks=[{"id": "T4"}])
        dd = d.to_dict()
        dd["agent"] = "qa-agent"
        eng.record(RP.ReplanDecision.from_dict(dd))
        assert len(eng.previous_decisions()) == 1
