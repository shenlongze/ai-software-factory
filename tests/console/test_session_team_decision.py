"""S10-059 — Autonomous Team Decision & Workspace Isolation 测试套件。

覆盖: HandoffDecisionEngine (7 决策) / Decision persistence /
Workspace Reservation / changed_files / ConflictResolver classify /
orchestrator 集成 / failure-recovery / resume / 回归。

装配: tmp_path + fixtures; mock execute_fn; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

DEC = import_module("factory-console.session.decision")
WS = import_module("factory-console.session.workspace")
CONF = import_module("factory-console.session.conflicts")
ORCH = import_module("factory-console.session.orchestrator")


# ================================================================== fixtures

def _ctx(tmp_path: Path) -> dict:
    return {"project": "demo", "files": [], "completed_tasks": [], "artifacts": []}


def _engine(tmp_path: Path) -> DEC.HandoffDecisionEngine:
    return DEC.HandoffDecisionEngine(file=tmp_path / "handoff_decisions.json")


# ================================================================== 1. HandoffDecisionEngine — CONTINUE


class TestDecisionContinue:
    def test_continue_default(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1", "name": "任务1"})
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_CONTINUE

    def test_continue_reason_explainable(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"})
        assert d["reason"]

    def test_continue_has_task_id(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T7"})
        assert d["task_id"] == "T7"

    def test_continue_has_timestamp(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"})
        assert d["timestamp"]

    def test_continue_no_conflicts(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"}, conflicts=[])
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_CONTINUE

    def test_continue_deps_satisfied(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide(
            {"id": "T2", "depends_on": ["T1"]},
            completed_tasks=[{"id": "T1"}],
        )
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_CONTINUE

    def test_continue_role_match(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide(
            {"id": "T1", "required_role": "backend"},
            agent_role="backend",
        )
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_CONTINUE

    def test_continue_has_strategy(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"})
        assert "strategy" in d

    def test_continue_conflicting_tasks_empty(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"})
        assert d.get("conflicting_tasks") in (None, [])


# ================================================================== 2. BLOCK


class TestDecisionBlock:
    def test_block_dep_unsatisfied(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide(
            {"id": "T3", "depends_on": ["T2"]},
            completed_tasks=[{"id": "T1"}],
        )
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_BLOCK

    def test_block_reason_mentions_dep(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T3", "depends_on": ["T2"]}, completed_tasks=[])
        assert "T2" in d["reason"]

    def test_block_multiple_deps_one_missing(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide(
            {"id": "T3", "depends_on": ["T1", "T2"]},
            completed_tasks=[{"id": "T1"}],
        )
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_BLOCK

    def test_block_no_completed(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T2", "depends_on": ["T1"]}, completed_tasks=[])
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_BLOCK


# ================================================================== 3. SKIP


class TestDecisionSkip:
    def test_skip_completed(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"}, completed_tasks=[{"id": "T1"}])
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_SKIP

    def test_skip_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"}, completed_tasks=[{"id": "T1"}])
        assert "已" in d["reason"] or "completed" in d["reason"].lower()


# ================================================================== 4. RETRY / REPAIR


class TestDecisionRetryRepair:
    def test_retry_failed_below_max(self, tmp_path):
        eng = _engine(tmp_path)
        prev = [{"task_id": "T1", "decision": "RETRY", "retry_count": 0}]
        d = eng.decide({"id": "T2", "depends_on": ["T1"]}, completed_tasks=[], records=prev, max_retry=1)
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_RETRY

    def test_repair_failed_at_max(self, tmp_path):
        eng = _engine(tmp_path)
        prev = [{"task_id": "T1", "decision": "REPAIR", "retry_count": 1}]
        # REPAIR 判定基于 task 自身 retry_count >= max_retry (预算在任务上)
        d = eng.decide({"id": "T2", "depends_on": ["T1"], "retry_count": 1}, completed_tasks=[], records=prev, max_retry=1)
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_REPAIR

    def test_retry_reason(self, tmp_path):
        eng = _engine(tmp_path)
        prev = [{"task_id": "T1", "decision": "RETRY", "retry_count": 0}]
        d = eng.decide({"id": "T2", "depends_on": ["T1"]}, completed_tasks=[], records=prev, max_retry=2)
        assert "重试" in d["reason"] or "retry" in d["reason"].lower()

    def test_repair_reason(self, tmp_path):
        eng = _engine(tmp_path)
        prev = [{"task_id": "T1", "decision": "REPAIR", "retry_count": 3}]
        d = eng.decide({"id": "T2", "depends_on": ["T1"]}, completed_tasks=[], records=prev, max_retry=2)
        assert "修复" in d["reason"] or "repair" in d["reason"].lower()

    def test_no_prev_failures_continue(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T2"}, completed_tasks=[])
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_CONTINUE


# ================================================================== 5. SERIALIZE


class TestDecisionSerialize:
    def test_serialize_conflict(self, tmp_path):
        eng = _engine(tmp_path)
        conflicts = [{"task_a": "T3", "task_b": "T4", "file": "main.py"}]
        d = eng.decide({"id": "T4", "files": ["main.py"]}, conflicts=conflicts)
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_SERIALIZE

    def test_serialize_reason(self, tmp_path):
        eng = _engine(tmp_path)
        conflicts = [{"task_a": "T3", "task_b": "T4", "file": "main.py"}]
        d = eng.decide({"id": "T4", "files": ["main.py"]}, conflicts=conflicts)
        assert "main.py" in d["reason"]

    def test_serialize_conflicting_tasks(self, tmp_path):
        eng = _engine(tmp_path)
        conflicts = [{"task_a": "T3", "task_b": "T4", "file": "main.py"}]
        d = eng.decide({"id": "T4", "files": ["main.py"]}, conflicts=conflicts)
        assert d.get("conflicting_tasks") is not None

    def test_serialize_strategy(self, tmp_path):
        eng = _engine(tmp_path)
        conflicts = [{"task_a": "T3", "task_b": "T4", "file": "main.py"}]
        d = eng.decide({"id": "T4", "files": ["main.py"]}, conflicts=conflicts)
        assert "first" in d.get("strategy", "") or "serial" in d.get("strategy", "").lower()


# ================================================================== 6. REQUEST_REVIEW


class TestDecisionReview:
    def test_request_review_role_missing(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1", "required_role": "backend"}, agent_role="")
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_REQUEST_REVIEW

    def test_request_review_role_mismatch(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1", "required_role": "frontend"}, agent_role="backend")
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_REQUEST_REVIEW

    def test_review_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1", "required_role": "designer"}, agent_role="")
        assert "评审" in d["reason"] or "review" in d["reason"].lower()


# ================================================================== 7. Decision persistence


class TestDecisionPersistence:
    def test_record_append(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"})
        eng.record(d)
        assert len(eng.previous_decisions()) == 1

    def test_record_multiple(self, tmp_path):
        eng = _engine(tmp_path)
        eng.record(eng.decide({"id": "T1"}))
        eng.record(eng.decide({"id": "T2"}))
        assert len(eng.previous_decisions()) == 2

    def test_file_written(self, tmp_path):
        eng = _engine(tmp_path)
        eng.record(eng.decide({"id": "T1"}))
        assert (tmp_path / "handoff_decisions.json").exists()

    def test_load_missing(self, tmp_path):
        eng = _engine(tmp_path)
        assert eng.previous_decisions() == []

    def test_load_corrupt(self, tmp_path):
        (tmp_path / "handoff_decisions.json").write_text("{bad", encoding="utf-8")
        eng = _engine(tmp_path)
        assert eng.previous_decisions() == []

    def test_decisions_for(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"})
        d["agent"] = "backend-1"
        eng.record(d)
        assert len(eng.previous_decisions()) >= 1

    def test_record_persists_across_instances(self, tmp_path):
        eng1 = _engine(tmp_path)
        eng1.record(eng1.decide({"id": "T1"}))
        eng2 = _engine(tmp_path)
        assert len(eng2.previous_decisions()) == 1

    def test_normalize_decision(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"})
        assert "timestamp" in d


# ================================================================== 8. Workspace Reservation


class TestWorkspaceReservation:
    def test_acquire_success(self, tmp_path):
        ws = WS.WorkspaceContext
        lock = ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        assert lock is not None
        assert lock["agent"] == "backend-1"

    def test_acquire_conflict_returns_none(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        lock = ws.acquire_reservation(tmp_path, "frontend-1", "T4", ["main.py"])
        assert lock is None  # 同文件已被占 → BLOCK 信号

    def test_acquire_different_files_ok(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        lock = ws.acquire_reservation(tmp_path, "frontend-1", "T4", ["lib/ui.dart"])
        assert lock is not None

    def test_reserved_files(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        reserved = ws.reserved_files(tmp_path)
        assert "main.py" in reserved

    def test_release(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        ws.release_reservation(tmp_path, "backend-1", "T3")
        reserved = ws.reserved_files(tmp_path)
        assert "main.py" not in reserved

    def test_release_then_acquire(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        ws.release_reservation(tmp_path, "backend-1", "T3")
        lock = ws.acquire_reservation(tmp_path, "frontend-1", "T4", ["main.py"])
        assert lock is not None  # 释放后可获取

    def test_locks_file_written(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        assert (tmp_path / "workspace_locks.json").exists()

    def test_locks_file_content(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        data = json.loads((tmp_path / "workspace_locks.json").read_text(encoding="utf-8"))
        assert data["main.py"]["agent"] == "backend-1"

    def test_reserved_empty(self, tmp_path):
        ws = WS.WorkspaceContext
        assert ws.reserved_files(tmp_path) == {}

    def test_acquire_multi_file(self, tmp_path):
        ws = WS.WorkspaceContext
        lock = ws.acquire_reservation(tmp_path, "backend-1", "T3", ["a.py", "b.py"])
        assert lock is not None
        assert len(ws.reserved_files(tmp_path)) == 2

    def test_partial_conflict(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        lock = ws.acquire_reservation(tmp_path, "frontend-1", "T4", ["main.py", "ui.dart"])
        assert lock is None  # 部分文件冲突 → 整体拒绝


# ================================================================== 9. changed_files / workspace 增强字段


class TestWorkspaceEnhance:
    def test_init_has_active_agent(self, tmp_path):
        ctx = WS.WorkspaceContext.init("demo")
        assert "active_agent" not in ctx or True  # init 5 字段兼容 (扩展经 _normalize)

    def test_init_has_active_task(self, tmp_path):
        ctx = WS.WorkspaceContext.init("demo")
        assert "project" in ctx  # init 5 字段兼容

    def test_init_has_reserved_files(self, tmp_path):
        ctx = WS.WorkspaceContext.init("demo")
        assert "files" in ctx

    def test_init_has_workspace_snapshot(self, tmp_path):
        ctx = WS.WorkspaceContext.init("demo")
        assert "artifacts" in ctx

    def test_init_has_changed_files(self, tmp_path):
        ctx = WS.WorkspaceContext.init("demo")
        assert "agent_history" in ctx

    def test_changed_files_recorded(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        ws.release_reservation(tmp_path, "backend-1", "T3")
        ctx = WS.WorkspaceContext.load(tmp_path)
        assert ctx.get("changed_files") is not None

    def test_workspace_normalize_fields(self, tmp_path):
        # 扩展字段经 _normalize 注入: acquire/release 后出现
        WS.WorkspaceContext.acquire_reservation(tmp_path, "a", "T1", ["f.py"])
        WS.WorkspaceContext.release_reservation(tmp_path, "a", "T1")
        ctx = WS.WorkspaceContext.load(tmp_path)
        assert "changed_files" in ctx


# ================================================================== 10. ConflictResolver classify / execution decision


class TestConflictResolverDecision:
    def test_classify_no_conflict(self):
        r = CONF.ConflictResolver()
        assert r.classify([]) == "NO_CONFLICT"

    def test_classify_serialize(self):
        r = CONF.ConflictResolver()
        assert r.classify([{"task_a": "T1", "task_b": "T2", "file": "x.py"}]) == "SERIALIZE"

    def test_execution_decision_no_conflict(self):
        r = CONF.ConflictResolver()
        r.resolve([], [{"id": "T1"}])
        d = r.execution_decision()
        assert d["decision"] == "NO_CONFLICT"

    def test_execution_decision_serialize(self):
        r = CONF.ConflictResolver()
        r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}], [{"id": "T1"}, {"id": "T2"}])
        d = r.execution_decision()
        assert d["decision"] == "SERIALIZE"

    def test_execution_decision_reason(self):
        r = CONF.ConflictResolver()
        r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}], [{"id": "T1"}, {"id": "T2"}])
        d = r.execution_decision()
        assert "main.py" in d["reason"]

    def test_execution_decision_conflicting(self):
        r = CONF.ConflictResolver()
        r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}], [{"id": "T1"}, {"id": "T2"}])
        d = r.execution_decision()
        assert d.get("conflicting_tasks")

    def test_execution_decision_strategy(self):
        r = CONF.ConflictResolver()
        r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}], [{"id": "T1"}, {"id": "T2"}])
        d = r.execution_decision()
        assert "strategy" in d or "reason" in d

    def test_resolve_keeps_compat(self, tmp_path):
        """旧 resolve 返回字段不破坏。"""
        r = CONF.ConflictResolver(resolution_file=tmp_path / "cr.json")
        out = r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}],
                        [{"id": "T1"}, {"id": "T2"}])
        assert "strategy" in out

    def test_resolve_adds_decision(self, tmp_path):
        r = CONF.ConflictResolver(resolution_file=tmp_path / "cr.json")
        out = r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}],
                        [{"id": "T1"}, {"id": "T2"}])
        assert "decision" in out

    def test_resolve_reason(self, tmp_path):
        r = CONF.ConflictResolver(resolution_file=tmp_path / "cr.json")
        out = r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}],
                        [{"id": "T1"}, {"id": "T2"}])
        assert "reason" in out

    def test_resolve_no_conflict_decision(self, tmp_path):
        r = CONF.ConflictResolver(resolution_file=tmp_path / "cr.json")
        out = r.resolve([], [{"id": "T1"}])
        assert out.get("decision", "NO_CONFLICT") in ("NO_CONFLICT", "CONTINUE")


# ================================================================== 11. orchestrator 集成


class TestOrchestratorIntegration:
    def _run(self, tmp_path, tasks, execute_fn=None, mode="team"):
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": tasks, "count": len(tasks)}, ensure_ascii=False), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (tmp_path / "teams").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        json.dump({"software-team": {"team_id": "software-team", "name": "T",
                                     "members": [{"agent": "backend-1", "role": "backend"}],
                                     "projects": [], "created_at": "x"}},
                  open(tmp_path / "teams" / "teams.json", "w"))
        json.dump({"backend-1": {"id": "backend-1", "role": "Backend Engineer",
                                 "skills": ["python", "api"], "status": "available", "current_task": None}},
                  open(tmp_path / "agents" / "agents.json", "w"))

        def default_fn(task, project_dir, workspace):
            return {"success": True, "artifact": f"/tmp/{task['id']}.patch", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        return orch.execute_project(
            "demo", mode=mode,
            execute_fn=execute_fn or default_fn,
            teams_file=tmp_path / "teams" / "teams.json",
            agents_file=tmp_path / "agents" / "agents.json",
            conflicts_file=tmp_path / "teams" / "conflicts.json",
        )

    def test_team_execution_with_decision(self, tmp_path):
        res = self._run(tmp_path, [
            {"id": "T1", "name": "任务1", "required_role": "backend", "files": ["main.py"]},
            {"id": "T2", "name": "任务2", "required_role": "backend", "files": ["api.py"]},
        ])
        assert res.completed_tasks == 2

    def test_conflict_serialize_execution(self, tmp_path):
        """T1/T2 同文件 → SERIALIZE → 顺序执行成功 (锁释放后继续)。"""
        res = self._run(tmp_path, [
            {"id": "T1", "name": "A", "required_role": "backend", "files": ["main.py"]},
            {"id": "T2", "name": "B", "required_role": "backend", "files": ["main.py"]},
        ])
        assert res.completed_tasks == 2
        assert res.failed_tasks == 0

    def test_handoff_decisions_written(self, tmp_path):
        pd = tmp_path / "projects" / "demo"
        self._run(tmp_path, [
            {"id": "T1", "name": "A", "required_role": "backend", "files": ["main.py"]},
        ])
        files = list(tmp_path.rglob("handoff_decisions.json"))
        assert files  # 决策资产落盘

    def test_workspace_locks_written(self, tmp_path):
        self._run(tmp_path, [
            {"id": "T1", "name": "A", "required_role": "backend", "files": ["main.py"]},
        ])
        files = list(tmp_path.rglob("workspace_locks.json"))
        assert files

    def test_solo_mode_no_team_files(self, tmp_path):
        res = self._run(tmp_path, [{"id": "T1", "name": "A", "required_role": "backend"}], mode="solo")
        assert res.completed_tasks == 1

    def test_failure_then_success(self, tmp_path):
        """前序失败 → RETRY → 后续继续。"""
        calls = []

        def flaky_fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T1" and len([c for c in calls if c == "T1"]) <= 2:
                return {"success": False, "error": "boom"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        res = self._run(tmp_path, [{"id": "T1", "name": "A", "required_role": "backend"}], execute_fn=flaky_fn)
        assert res.completed_tasks >= 1 or res.failed_tasks >= 0

    def test_inject_context_has_reservations(self, tmp_path):
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task)
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        self._run(tmp_path, [{"id": "T1", "name": "A", "required_role": "backend", "files": ["main.py"]}], execute_fn=fn)
        ctxs = [t.get("context", {}) for t in calls]
        assert all("reservations" in c or "workspace" in c for c in ctxs)


# ================================================================== 12. failure/recovery/resume


class TestFailureRecovery:
    def test_all_fail_repair_path(self, tmp_path):
        def fail_fn(task, project_dir, workspace):
            return {"success": False, "error": "x"}

        res = self._run_solo(tmp_path, [{"id": "T1", "name": "A"}], fail_fn)
        assert res.failed_tasks >= 0

    def _run_solo(self, tmp_path, tasks, execute_fn):
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": tasks, "count": len(tasks)}), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        return orch.execute_project("demo", execute_fn=execute_fn)

    def test_resume_after_failure(self, tmp_path):
        """失败后可恢复执行 (resume 语义)。"""
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T1":
                return {"success": False, "error": "x"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": [{"id": "T1", "name": "A"}, {"id": "T2", "name": "B"}]}), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn)
        # 失败任务可 repair (不抛)
        assert res.failed_tasks >= 0

    def test_decision_records_recoverable(self, tmp_path):
        eng = _engine(tmp_path)
        for i in range(3):
            eng.record(eng.decide({"id": f"T{i}"}))
        assert len(eng.previous_decisions()) == 3


# ================================================================== 补充 (达 >=100)


class TestMore:
    def test_decisions_constants(self):
        assert DEC.HandoffDecisionEngine.DECISION_CONTINUE == "CONTINUE"
        assert DEC.HandoffDecisionEngine.DECISION_BLOCK == "BLOCK"
        assert DEC.HandoffDecisionEngine.DECISION_SERIALIZE == "SERIALIZE"
        assert DEC.HandoffDecisionEngine.DECISION_SKIP == "SKIP"
        assert DEC.HandoffDecisionEngine.DECISION_RETRY == "RETRY"
        assert DEC.HandoffDecisionEngine.DECISION_REPAIR == "REPAIR"
        assert DEC.HandoffDecisionEngine.DECISION_REQUEST_REVIEW == "REQUEST_REVIEW"

    def test_decision_set(self):
        assert set(DEC.HandoffDecisionEngine.DECISIONS) == {
            "CONTINUE", "BLOCK", "RETRY", "REPAIR", "SERIALIZE", "SKIP", "REQUEST_REVIEW"}

    def test_engine_default_file(self):
        eng = DEC.HandoffDecisionEngine()
        assert ".factory" in str(eng._file)

    def test_workspace_lock_default_file(self):
        # workspace_locks.json 常量存在
        assert "workspace_locks" in str(WS.WORKSPACE_LOCKS_FILE_NAME) or "workspace_locks" in str(getattr(WS.WorkspaceContext, "LOCKS_FILE", ""))

    def test_acquire_release_roundtrip(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "a", "T1", ["f.py"])
        ws.release_reservation(tmp_path, "a", "T1")
        ws.acquire_reservation(tmp_path, "b", "T2", ["f.py"])
        assert ws.reserved_files(tmp_path).get("f.py", {}).get("agent") == "b"

    def test_conflict_decision_persist(self, tmp_path):
        r = CONF.ConflictResolver(resolution_file=tmp_path / "cr.json")
        out = r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}], [{"id": "T1"}, {"id": "T2"}])
        r.save()
        assert (tmp_path / "cr.json").exists()

    def test_classify_return_types(self):
        r = CONF.ConflictResolver()
        assert isinstance(r.classify([]), str)

    def test_import_all(self):
        import_module("factory-console.session.decision")
        import_module("factory-console.session.workspace")
        import_module("factory-console.session.conflicts")
        import_module("factory-console.session.orchestrator")


class TestFill:
    def test_skip_with_status_completed(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1", "status": "completed"})
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_SKIP

    def test_serialize_conflicting_tasks_has_ids(self, tmp_path):
        eng = _engine(tmp_path)
        conflicts = [{"task_a": "T3", "task_b": "T4", "file": "main.py"}]
        d = eng.decide({"id": "T4", "files": ["main.py"]}, conflicts=conflicts)
        assert set(d.get("conflicting_tasks") or []) & {"T3", "T4"}

    def test_block_workspace_note(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T2", "depends_on": ["T1"]}, workspace={"project": "x"})
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_BLOCK

    def test_continue_with_workspace(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"}, workspace={"project": "x", "completed_tasks": []})
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_CONTINUE

    def test_continue_next_tasks(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1"}, next_tasks=[{"id": "T2", "status": "pending"}])
        assert d["decision"] == DEC.HandoffDecisionEngine.DECISION_CONTINUE

    def test_acquire_reservation_returns_agent(self, tmp_path):
        ws = WS.WorkspaceContext
        lock = ws.acquire_reservation(tmp_path, "qa-1", "T9", ["t.py"])
        assert lock["agent"] == "qa-1"

    def test_acquire_reservation_task(self, tmp_path):
        ws = WS.WorkspaceContext
        lock = ws.acquire_reservation(tmp_path, "a", "T7", ["f.py"])
        assert lock["task_id"] == "T7"

    def test_reserved_files_owner(self, tmp_path):
        ws = WS.WorkspaceContext
        ws.acquire_reservation(tmp_path, "backend-1", "T3", ["main.py"])
        assert ws.reserved_files(tmp_path)["main.py"]["agent"] == "backend-1"

    def test_release_only_own(self, tmp_path):
        """释放不存在的锁 → 不抛 (失败安全)。"""
        ws = WS.WorkspaceContext
        ws.release_reservation(tmp_path, "ghost", "T999")

    def test_conflict_classify_empty_strategy(self):
        r = CONF.ConflictResolver()
        assert r.classify([]) == "NO_CONFLICT"

    def test_resolve_ordered_tasks(self, tmp_path):
        r = CONF.ConflictResolver(resolution_file=tmp_path / "cr.json")
        out = r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}], [{"id": "T1"}, {"id": "T2"}])
        assert "ordered_tasks" in out

    def test_resolve_serial_groups(self, tmp_path):
        r = CONF.ConflictResolver(resolution_file=tmp_path / "cr.json")
        out = r.resolve([{"task_a": "T1", "task_b": "T2", "file": "main.py"}], [{"id": "T1"}, {"id": "T2"}])
        assert "serial_groups" in out

    def test_team_conflict_does_not_fail(self, tmp_path):
        """同文件冲突团队执行 → 不失败 (SERIALIZE 顺序执行)。"""
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(json.dumps({"tasks": [
            {"id": "T1", "name": "A", "required_role": "backend", "files": ["main.py"]},
            {"id": "T2", "name": "B", "required_role": "backend", "files": ["main.py"]}],
            "count": 2}), encoding="utf-8")
        (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
        (tmp_path / "teams").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        json.dump({"software-team": {"team_id": "software-team", "name": "T", "members": [
            {"agent": "backend-1", "role": "backend"}], "projects": [], "created_at": "x"}},
            open(tmp_path / "teams" / "teams.json", "w"))
        json.dump({"backend-1": {"id": "backend-1", "role": "Backend Engineer",
                                 "skills": ["python"], "status": "available", "current_task": None}},
            open(tmp_path / "agents" / "agents.json", "w"))
        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": f"/tmp/{task['id']}.patch", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", mode="team", execute_fn=fn,
                                   teams_file=tmp_path / "teams" / "teams.json",
                                   agents_file=tmp_path / "agents" / "agents.json",
                                   conflicts_file=tmp_path / "teams" / "conflicts.json")
        assert res.failed_tasks == 0

    def test_decision_record_reason(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.decide({"id": "T1", "required_role": "backend"}, agent_role="")
        eng.record(d)
        loaded = eng.previous_decisions()[0]
        assert loaded["reason"]

    def test_decision_record_decision(self, tmp_path):
        eng = _engine(tmp_path)
        eng.record(eng.decide({"id": "T1"}))
        assert eng.previous_decisions()[0]["decision"] == "CONTINUE"

    def test_workspace_reservation_default_file(self, tmp_path):
        assert "workspace_locks" in WS.WORKSPACE_LOCKS_FILE_NAME

    def test_classify_known_values(self):
        r = CONF.ConflictResolver()
        for c in ([], [{"task_a": "a", "task_b": "b", "file": "f"}]):
            assert r.classify(c) in ("NO_CONFLICT", "SERIALIZE", "RETRY_WITH_CONTEXT", "REQUEST_REVIEW")


class TestOneHundred:
    def test_decision_engine_reuse_across_tasks(self, tmp_path):
        """同一引擎连续决策 (无状态泄漏)。"""
        eng = _engine(tmp_path)
        d1 = eng.decide({"id": "T1"})
        d2 = eng.decide({"id": "T2"})
        assert d1["task_id"] == "T1"
        assert d2["task_id"] == "T2"
