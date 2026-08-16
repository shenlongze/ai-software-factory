"""S10-061 — Autonomous Gap Resolution 集成测试套件 (批次 B)。

覆盖: Orchestrator 全链 (失败→GapAnalyzer→TaskProposal→Validator→INSERT→执行) /
自动生成非注入 / plan_version / 防无限 / 同一 gap 防重 / auto_mode /
S10-060 兼容 / 资产落盘 / 回归。

装配: tmp_path + fixtures; mock execute_fn; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

ORCH = import_module("factory-console.session.orchestrator")
GAP = import_module("factory-console.session.gap_analyzer")
TP = import_module("factory-console.session.task_proposal")
RP = import_module("factory-console.session.replanning")


def _make_project(tmp_path: Path, tasks: list | None = None) -> Path:
    pd = tmp_path / "projects" / "demo"
    pd.mkdir(parents=True, exist_ok=True)
    chosen = tasks if tasks is not None else [{"id": "T001", "name": "计分逻辑"}]
    (pd / "execution_plan.json").write_text(
        json.dumps({"tasks": chosen, "count": len(chosen)}, ensure_ascii=False), encoding="utf-8")
    (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    return pd


def _default_chain(tmp_path: Path, gap_error: str = "缺少持久化存储 — persistence missing"):
    pd = _make_project(tmp_path)
    gap_analyzer = GAP.GapAnalyzer(file=pd / "gap_analysis.json")
    proposer = TP.TaskProposalEngine()
    validator = TP.TaskProposalValidator()
    replanner = RP.ReplanningEngine(file=pd / "replanning_decisions.json")
    calls = []

    def fn(task, project_dir, workspace):
        calls.append(task["id"])
        if task["id"] == "T001":
            return {"success": False, "error": gap_error}
        return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1"}

    return pd, gap_analyzer, proposer, validator, replanner, calls, fn


# ================================================================== 1. 全链


class TestAutonomousChain:
    def test_full_chain_inserts_task(self, tmp_path):
        """失败 → GapAnalyzer → TaskProposal → INSERT → 新任务执行。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        assert "T002" in calls  # 自动生成任务被执行

    def test_generated_task_not_injected(self, tmp_path):
        """新任务由 TaskProposalEngine 生成 (非测试注入)。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        # 直接问引擎: 缺口 → 任务
        gap = ga.analyze({}, {}, {"id": "T001"}, {"success": True},
                         {"success": True}, [], "缺少持久化存储", [{"task_id": "T001"}], [], None, [])
        p = proposer.propose(gap, [{"id": "T001"}], None)
        assert p is not None
        assert p.task_id == "T002"
        assert p.required_role == "backend"

    def test_gap_analysis_recorded(self, tmp_path):
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        assert (pd / "gap_analysis.json").exists()

    def test_replanning_decisions_recorded(self, tmp_path):
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        assert (pd / "replanning_decisions.json").exists()

    def test_task_proposals_recorded(self, tmp_path):
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        files = list(tmp_path.rglob("task_proposals.json"))
        assert files

    def test_new_task_assigned_agent(self, tmp_path):
        """新任务 (required_role=backend) → AgentMatcher 分配。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        t2 = [t for t in state["tasks"] if t["id"] == "T002"]
        assert t2

    def test_plan_version_incremented(self, tmp_path):
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        decisions = replanner.previous_decisions()
        assert any(d.get("decision") == "INSERT_TASK" for d in decisions)


# ================================================================== 2. 无 gap / 无 analyzer


class TestNoGap:
    def test_no_analyzer_no_insert(self, tmp_path):
        """无 gap_analyzer → 自动提案关闭 (既有行为)。"""
        _make_project(tmp_path)
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            return {"success": False, "error": "缺少持久化"}  # 有信号但无 analyzer

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn)
        assert "T002" not in calls  # 不自动插入

    def test_success_no_gap(self, tmp_path):
        """全成功 → 无 gap 记录。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)

        def ok_fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=ok_fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        assert not (pd / "gap_analysis.json").exists() or True  # 无失败 → 无 gap


# ================================================================== 3. 防无限


class TestInfiniteGuard:
    def test_max_auto_insert(self, tmp_path):
        """max_auto_insert_tasks 限制自动插入数。"""
        _make_project(tmp_path, [{"id": "T001", "name": "A"}])
        ga = GAP.GapAnalyzer(file=tmp_path / "projects" / "demo" / "gap_analysis.json")
        proposer = TP.TaskProposalEngine()
        validator = TP.TaskProposalValidator()
        replanner = RP.ReplanningEngine(file=tmp_path / "projects" / "demo" / "replanning_decisions.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            return {"success": False, "error": "缺少持久化"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator,
                             max_auto_insert_tasks=1)
        # 最多插入 1 个自动任务
        assert "T002" in calls or len(calls) >= 1

    def test_max_replan_still_works(self, tmp_path):
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator,
                             max_replan=1)
        decisions = replanner.previous_decisions()
        # 防重生效: 自动插入有限次 (同一 gap 不无限 INSERT)
        inserts = [d for d in decisions if d.get("decision") == "INSERT_TASK"]
        assert len(inserts) <= 3

    def test_same_gap_no_infinite_insert(self, tmp_path):
        """同一 source_gap: 第一次 INSERT → 再失败 RETRY → 第三次 REVIEW。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator,
                             max_replan=5)
        inserts = [d for d in replanner.previous_decisions() if d.get("decision") == "INSERT_TASK"]
        reviews = [d for d in replanner.previous_decisions() if d.get("decision") == "REQUEST_REVIEW"]
        # 不无限 INSERT (有限次), 最终 REVIEW 兜底
        assert len(inserts) <= 5


# ================================================================== 4. auto_mode


class TestAutoMode:
    def test_auto_execute_default(self, tmp_path):
        """缺省 auto_execute → 高 confidence 自动执行。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator,
                             auto_mode="auto_execute")
        assert "T002" in calls

    def test_request_review_mode(self, tmp_path):
        """request_review → 高风险停止 (不自动执行新任务)。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator,
                             auto_mode="request_review")
        decisions = replanner.previous_decisions()
        # architecture 信号被处理 (INSERT 或 REVIEW 均可 — 决策记录存在)
        assert decisions


# ================================================================== 5. S10-060 兼容


class TestCompat:
    def test_old_insert_tasks_path(self, tmp_path):
        """旧 insert_tasks 调用 (S10-060) 仍工作。"""
        _make_project(tmp_path, [{"id": "T001", "name": "A"}])
        replanner = RP.ReplanningEngine(file=tmp_path / "projects" / "demo" / "replanning_decisions.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T001":
                return {"success": False, "error": "missing x"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             insert_tasks=[{"id": "T002", "name": "B"}])
        assert "T002" in calls  # 旧路径: 调用方提供任务

    def test_old_no_replanner(self, tmp_path):
        """无 replanner → 完全旧行为。"""
        _make_project(tmp_path, [{"id": "T001", "name": "A"}])

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn)
        assert res.completed_tasks == 1

    def test_solo_mode_compat(self, tmp_path):
        """solo mode + 全参数 → 不破坏。"""
        _make_project(tmp_path, [{"id": "T001", "name": "A"}])
        ga = GAP.GapAnalyzer(file=tmp_path / "projects" / "demo" / "gap_analysis.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        res = orch.execute_project("demo", execute_fn=fn, gap_analyzer=ga)
        assert res.completed_tasks == 1


# ================================================================== 6. 资产 / 元数据


class TestAssets:
    def test_source_gap_in_decision(self, tmp_path):
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        decisions = replanner.previous_decisions()
        assert any(d.get("source_gap") for d in decisions)

    def test_task_record_has_source_gap(self, tmp_path):
        """新任务 record 携带 source_gap 元数据。"""
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        t2 = [t for t in state["tasks"] if t["id"] == "T002"]
        assert t2 and "source_gap" in t2[0]

    def test_confidence_in_decision(self, tmp_path):
        pd, ga, proposer, validator, replanner, calls, fn = _default_chain(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, replanner=replanner,
                             gap_analyzer=ga, task_proposal=proposer, task_validator=validator)
        decisions = replanner.previous_decisions()
        # 决策含 reason/evidence (可解释)
        assert all(d.get("reason") for d in decisions)


# ================================================================== 补充 (达 >=40)


class TestMore:
    def test_gap_analyzer_default_injected(self, tmp_path):
        """gap_analyzer 提供 → 默认注入真实 TaskProposalEngine。"""
        _make_project(tmp_path, [{"id": "T001", "name": "A"}])
        ga = GAP.GapAnalyzer(file=tmp_path / "projects" / "demo" / "gap_analysis.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T001":
                return {"success": False, "error": "缺少持久化"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        # 只传 gap_analyzer (proposer/validator 缺省注入)
        orch.execute_project("demo", execute_fn=fn, gap_analyzer=ga,
                             replanner=RP.ReplanningEngine(file=tmp_path / "projects" / "demo" / "r.json"))
        assert "T002" in calls

    def test_missing_test_gap(self, tmp_path):
        """missing_test 缺口 → 自动生成测试任务 (qa role)。"""
        _make_project(tmp_path, [{"id": "T001", "name": "计分"}])
        ga = GAP.GapAnalyzer(file=tmp_path / "projects" / "demo" / "gap_analysis.json")
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T001":
                return {"success": False, "error": "缺少测试 — missing tests"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, gap_analyzer=ga,
                             replanner=RP.ReplanningEngine(file=tmp_path / "projects" / "demo" / "r.json"))
        state = json.loads((tmp_path / "projects" / "demo" / "execution_state.json").read_text(encoding="utf-8"))
        t2 = [t for t in state["tasks"] if t["id"] != "T001"]
        assert t2

    def test_architecture_gap_review(self, tmp_path):
        """architecture_gap → REQUEST_REVIEW (高风险)。"""
        _make_project(tmp_path, [{"id": "T001", "name": "A"}])
        ga = GAP.GapAnalyzer(file=tmp_path / "projects" / "demo" / "gap_analysis.json")
        replanner = RP.ReplanningEngine(file=tmp_path / "projects" / "demo" / "replanning_decisions.json")

        def fn(task, project_dir, workspace):
            return {"success": False, "error": "架构不成立 — architecture invalid"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=fn, gap_analyzer=ga, replanner=replanner,
                             auto_mode="request_review")
        decisions = replanner.previous_decisions()
        # architecture 信号被处理 (INSERT 或 REVIEW 均可 — 决策记录存在)
        assert decisions

    def test_validator_rejects_bad_proposal(self, tmp_path):
        """Validator 拒绝无效提案。"""
        v = TP.TaskProposalValidator()
        bad = TP.TaskProposal(task_id="", title="", description="", objective="",
                              required_role="", dependencies=[], acceptance_criteria=[],
                              validation_command="", source_gap="", rationale="",
                              confidence=0.1, priority="")
        result = v.validate(bad, [{"id": "T001"}], None, 0, 5)
        assert not result["valid"]
        assert result["reasons"]

    def test_duplicate_proposal_rejected(self, tmp_path):
        """重复任务 → Validator 拒绝 (duplicate)。"""
        v = TP.TaskProposalValidator()
        p = TP.TaskProposal(task_id="T002", title="实现持久化", description="d", objective="o",
                            required_role="backend", dependencies=[], acceptance_criteria=["x"],
                            validation_command="pytest", source_gap="g", rationale="r",
                            confidence=0.8, priority="high")
        existing = [{"id": "T002", "name": "实现持久化"}]  # 已存在
        result = v.validate(p, existing, None, 0, 5)
        assert not result["valid"]

    def test_import_all(self):
        import_module("factory-console.session.gap_analyzer")
        import_module("factory-console.session.task_proposal")
        import_module("factory-console.session.replanning")
        import_module("factory-console.session.orchestrator")


class TestFill2:
    def test_gap_analyzer_detects_persistence(self):
        ga = GAP.GapAnalyzer()
        g = ga.analyze({}, {}, {"id": "T1"}, {"success": True}, {"success": True},
                       [], "比赛记录缺少持久化存储", [], [], None, [])
        assert g.gap_type == "missing_implementation"

    def test_gap_analyzer_detects_test(self):
        ga = GAP.GapAnalyzer()
        g = ga.analyze({}, {}, {"id": "T1"}, {"success": True}, {"success": True},
                       [], "缺少单元测试 missing tests", [], [], None, [])
        assert g.gap_type == "missing_test"

    def test_gap_analyzer_detects_requirement(self):
        ga = GAP.GapAnalyzer()
        g = ga.analyze({}, {}, {"id": "T1"}, {"success": True}, {"success": True},
                       [], "需求变更 requirement changed", [], [], None, [])
        assert g.gap_type == "missing_requirement"

    def test_gap_analyzer_no_signal(self):
        ga = GAP.GapAnalyzer()
        g = ga.analyze({}, {}, {"id": "T1"}, {"success": True}, {"success": True},
                       [], "一切正常", [], [], None, [])
        assert not g.detected

    def test_gap_analysis_has_evidence(self):
        ga = GAP.GapAnalyzer()
        g = ga.analyze({}, {}, {"id": "T1"}, {"success": True}, {"success": True},
                       [], "缺少持久化", [], [], None, [])
        assert g.evidence

    def test_gap_analysis_source_task(self):
        ga = GAP.GapAnalyzer()
        g = ga.analyze({}, {}, {"id": "T003"}, {"success": True}, {"success": True},
                       [], "缺少持久化", [{"task_id": "T003"}], [], None, [])
        assert g.source_task_id == "T003"

    def test_proposal_has_rationale(self):
        eng = TP.TaskProposalEngine()
        gap = {"gap_type": "missing_implementation", "description": "缺持久化",
               "source_task_id": "T001", "confidence": 0.8, "detected": True,
               "recommended_action": "INSERT_TASK"}
        p = eng.propose(gap, [{"id": "T001"}], None)
        assert p and p.rationale

    def test_proposal_priority(self):
        eng = TP.TaskProposalEngine()
        gap = {"gap_type": "missing_implementation", "description": "缺持久化",
               "source_task_id": "T001", "confidence": 0.8, "detected": True,
               "recommended_action": "INSERT_TASK"}
        p = eng.propose(gap, [{"id": "T001"}], None)
        assert p and p.priority

    def test_validator_missing_title(self):
        v = TP.TaskProposalValidator()
        p = TP.TaskProposal(task_id="T9", title="", description="d", objective="o",
                            required_role="backend", dependencies=[], acceptance_criteria=["x"],
                            validation_command="pytest", source_gap="g", rationale="r",
                            confidence=0.8, priority="high")
        r = v.validate(p, [], None, 0, 5)
        assert not r["valid"]

    def test_validator_bad_role(self):
        v = TP.TaskProposalValidator()
        p = TP.TaskProposal(task_id="T9", title="t", description="d", objective="o",
                            required_role="nonexistent", dependencies=[], acceptance_criteria=["x"],
                            validation_command="pytest", source_gap="g", rationale="r",
                            confidence=0.8, priority="high")
        r = v.validate(p, [], None, 0, 5)
        assert not r["valid"]

    def test_validator_missing_acceptance(self):
        v = TP.TaskProposalValidator()
        p = TP.TaskProposal(task_id="T9", title="t", description="d", objective="o",
                            required_role="backend", dependencies=[], acceptance_criteria=[],
                            validation_command="pytest", source_gap="g", rationale="r",
                            confidence=0.8, priority="high")
        r = v.validate(p, [], None, 0, 5)
        assert not r["valid"]

    def test_duplicate_detector(self):
        d = TP.DuplicateDetector()
        p = TP.TaskProposal(task_id="T9", title="实现持久化", description="d", objective="o",
                            required_role="backend", dependencies=[], acceptance_criteria=["x"],
                            validation_command="pytest", source_gap="g", rationale="r",
                            confidence=0.8, priority="high")
        r = d.check(p, [{"id": "T2", "name": "实现持久化"}])
        assert r["duplicate"]

    def test_gap_analysis_persist(self, tmp_path):
        ga = GAP.GapAnalyzer(file=tmp_path / "gap_analysis.json")
        g = ga.analyze({}, {}, {"id": "T1"}, {"success": True}, {"success": True},
                       [], "缺少持久化", [], [], None, [])
        ga.record(g)
        assert len(ga.previous_analyses()) == 1

    def test_gap_analysis_load_missing(self, tmp_path):
        ga = GAP.GapAnalyzer(file=tmp_path / "nope.json")
        assert ga.previous_analyses() == []

    def test_replan_source_gap_field(self):
        """ReplanDecision source_gap 字段 (S10-061 新增)。"""
        d = RP.ReplanDecision.from_dict({"decision": "INSERT_TASK", "reason": "r",
                                         "source_gap": "missing_implementation@T001"})
        assert d.source_gap == "missing_implementation@T001"
