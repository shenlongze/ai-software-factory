"""tests/console/test_evidence_attach.py — EvidenceBundle 接入普通执行 (M1b/T3)。

覆盖: from_execution_result 组装 (日志/测试/决策/产物, diff 不伪造) /
ExecutionOrchestrator.execute_project 完成后自动组装证据包 (复用 from_repo_result
模式) + logs 执行事件摘要 (T4) / 失败安全 (证据包不阻断执行)。
basename 全仓库唯一。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

EV = import_module("factory-console.session.evidence")
ORCH = import_module("factory-console.session.orchestrator")

PLAN_TASKS: list[dict] = [
    {"id": "T001", "name": "数据库 Schema 设计", "agent_type": "backend", "agent": "backend-1"},
    {"id": "T002", "name": "测试用例编写", "agent_type": "qa", "agent": "backend-1"},
]


def _make_project(root: Path, slug: str = "demo") -> Path:
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "execution_plan.json").write_text(
        json.dumps({"tasks": PLAN_TASKS, "count": len(PLAN_TASKS)}), encoding="utf-8"
    )
    (pdir / "project.json").write_text(
        json.dumps({"name": "Demo", "status": "execution_ready"}), encoding="utf-8"
    )
    (pdir / "product.json").write_text(
        json.dumps({
            "name": "Demo", "problem": "p", "user": "u", "platform": "mobile",
            "core_features": ["f"], "status": "execution_ready",
        }),
        encoding="utf-8",
    )
    return pdir


def _ok_fn(calls: list | None = None):
    def fn(task, project_dir, workspace):
        if calls is not None:
            calls.append(task)
        return {"success": True, "artifact": f"art-{task.get('id')}", "cost": "0.01"}
    return fn


class _FakeResult:
    """orchestrator.ExecutionResult 形状 (组装测试用)。"""

    project = "demo"
    status = "delivered"
    completed_tasks = 2
    failed_tasks = 0
    artifacts = ["art-T001", "art-T002"]
    duration = 1.5
    cost = "0.01"
    errors = []

    def to_dict(self):
        return {
            "project": self.project,
            "status": self.status,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "artifacts": list(self.artifacts),
            "duration": self.duration,
            "cost": self.cost,
            "errors": list(self.errors),
        }


class TestFromExecutionResult:
    def test_assembles_logs_test_decisions(self):
        b = EV.EvidenceBuilder.from_execution_result(_FakeResult(), project_id="demo")
        assert b.bundle_id.startswith("ev-")
        assert b.project_id == "demo"
        assert b.agent_id == "orchestrator"
        assert b.task_id == "demo"
        assert b.diff == ""  # 普通执行无 unified patch — 不伪造
        assert b.test_results[0]["ok"] is True
        assert b.artifacts == ["art-T001", "art-T002"]
        # T4: 执行日志 (执行事件摘要)
        assert any(log["step"] == "execute" for log in b.logs)
        assert any(log["step"] == "lifecycle" for log in b.logs)
        assert b.decisions[0]["step"] == "execute"

    def test_failed_result_reflected(self):
        r = _FakeResult()
        r.status = "failed"
        r.failed_tasks = 1
        r.errors = ["T001: boom"]
        b = EV.EvidenceBuilder.from_execution_result(r, project_id="demo")
        assert b.test_results[0]["ok"] is False
        assert any("失败" in str(log.get("summary")) for log in b.logs)
        assert "boom" in b.decisions[0]["reason"]

    def test_explicit_logs_override(self):
        logs = [{"step": "custom", "ts": "t", "summary": "s"}]
        b = EV.EvidenceBuilder.from_execution_result(
            _FakeResult(), project_id="demo", logs=logs,
            test_results=[{"ok": True, "output": "x"}],
        )
        assert b.logs == logs
        assert b.test_results == [{"ok": True, "output": "x"}]

    def test_logs_from_steps_fail_safe(self):
        assert EV.EvidenceBuilder.logs_from_steps([]) == []
        assert EV.EvidenceBuilder.logs_from_steps([("a", "b")])[0]["step"] == "a"


class TestExecuteProjectAttach:
    """普通执行 (execute_project) 完成后自动组装证据包 (T3 验收 2)。"""

    def test_evidence_bundle_created_after_execute(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        result = orch.execute_project("demo", execute_fn=_ok_fn())
        assert result.completed_tasks == 2
        assert result.failed_tasks == 0
        # 证据包落盘 + 日志 (T4)
        bundles = EV.EvidenceStore(tmp_path, "demo").list()
        assert len(bundles) == 1
        b = bundles[0]
        assert b.project_id == "demo"
        assert b.agent_id == "orchestrator"
        assert b.artifacts == ["art-T001", "art-T002"]
        assert b.test_results[0]["ok"] is True
        steps = [log.get("step") for log in b.logs]
        assert "execute" in steps
        assert any(s.startswith("task:") for s in steps)
        assert "validation" in steps
        # 审计事件
        events = json.loads(
            (tmp_path / "audit" / "audit_events.json").read_text(encoding="utf-8")
        )
        assert any(e.get("event_type") == "EVIDENCE_BUNDLE_CREATED" for e in events)

    def test_failed_execution_still_attaches(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)

        def fail_fn(task, project_dir, workspace):
            return {"success": False, "error": "boom"}

        result = orch.execute_project("demo", execute_fn=fail_fn)
        assert result.failed_tasks > 0
        bundles = EV.EvidenceStore(tmp_path, "demo").list()
        assert len(bundles) == 1
        assert bundles[0].test_results[0]["ok"] is False
