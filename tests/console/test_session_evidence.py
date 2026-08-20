"""test_session_evidence.py — EvidenceBundle 证据包 (M1a/E1)。

覆盖: 组装 (build/from_repo_result) / 持久化 (save/load/list) /
审计事件 (EVIDENCE_BUNDLE_CREATED 落盘)。basename 全仓库唯一。
"""

from __future__ import annotations

import json

from importlib import import_module

EV = import_module("factory-console.session.evidence")


class _RepoResult:
    target = "加一个导出"
    plan_reason = "计划: 改 main.py"
    changed_files = ["main.py"]
    test_ok = True
    test_output = "2 passed"
    _patch_text = "--- a/main.py\n+++ b/main.py\n"


class TestEvidenceBuilder:
    def test_build_fields(self):
        b = EV.EvidenceBuilder.build(
            project_id="p1", task_id="t1", agent_id="repo",
            diff="--- a/x", test_results=[{"ok": True, "output": "1 passed"}],
            decisions=[{"step": "plan", "reason": "r"}], artifacts=["main.py"],
        )
        assert b.bundle_id.startswith("ev-")
        assert b.project_id == "p1"
        assert b.status == "pending"
        assert b.test_results[0]["ok"] is True
        assert "main.py" in b.artifacts

    def test_from_repo_result(self):
        b = EV.EvidenceBuilder.from_repo_result(_RepoResult(), project_id="slug")
        assert b.diff == "--- a/main.py\n+++ b/main.py\n"
        assert b.test_results[0]["ok"] is True
        assert b.decisions[0]["step"] == "plan"
        assert b.artifacts == ["main.py"]

    def test_roundtrip_dict(self):
        b = EV.EvidenceBuilder.build(project_id="p", diff="d")
        data = b.to_dict()
        back = EV.EvidenceBundle.from_dict(data)
        assert back.bundle_id == b.bundle_id
        assert back.status == "pending"


class TestEvidenceStore:
    def test_save_load_list(self, tmp_path):
        store = EV.EvidenceStore(tmp_path, "slug")
        b1 = EV.EvidenceBuilder.build(project_id="slug", task_id="t1")
        b2 = EV.EvidenceBuilder.build(project_id="slug", task_id="t2")
        store.save(b1)
        store.save(b2)
        assert store.load(b1.bundle_id).task_id == "t1"
        assert {b.task_id for b in store.list()} == {"t1", "t2"}
        assert (tmp_path / "projects" / "slug" / "evidence" / f"{b1.bundle_id}.json").is_file()

    def test_load_missing_none(self, tmp_path):
        assert EV.EvidenceStore(tmp_path, "slug").load("ev-nope") is None


class TestEvidenceAudit:
    def test_emit_creates_audit_event(self, tmp_path):
        b = EV.EvidenceBuilder.build(project_id="slug", agent_id="repo")
        EV.emit_evidence_created(tmp_path, b)
        events = json.loads((tmp_path / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert any(e.get("event_type") == "EVIDENCE_BUNDLE_CREATED" for e in events)
        assert events[-1]["event_type"] == "EVIDENCE_BUNDLE_CREATED"
