"""S10-063 批次 A — ReviewRecord + ReviewGate 测试套件。

覆盖: request (open) / approve / reject / cancel / pending / status
(none/waiting/approved/rejected) / 持久化 / 失败安全。

装配: tmp_path; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

RG = import_module("factory-console.session.review_gate")


def _gate(tmp_path: Path) -> RG.ReviewGate:
    return RG.ReviewGate(file=tmp_path / "review_records.json")


# ================================================================== 1. request


class TestRequest:
    def test_request_creates_open_record(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="超预算", trigger="budget")
        assert rec.status == RG.STATUS_OPEN
        assert rec.review_id

    def test_request_fields(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(
            reason="高风险重构",
            trigger="policy",
            context={"phase": "execution"},
            affected_tasks=["T1", "T2"],
            estimated_cost=12.5,
            risk="high",
        )
        assert rec.reason == "高风险重构"
        assert rec.trigger == "policy"
        assert rec.context.get("phase") == "execution"
        assert rec.affected_tasks == ["T1", "T2"]
        assert rec.estimated_cost == pytest.approx(12.5)
        assert rec.risk == "high"

    def test_request_timestamp(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        assert rec.created_at

    def test_request_project_id_in_context(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r", project_id="p1")
        assert rec.context.get("project_id") == "p1"

    def test_request_persisted(self, tmp_path):
        gate = _gate(tmp_path)
        gate.request(reason="r")
        data = json.loads(
            (tmp_path / "review_records.json").read_text(encoding="utf-8")
        )
        assert len(data) == 1
        assert data[0]["status"] == "open"

    def test_request_unique_ids(self, tmp_path):
        gate = _gate(tmp_path)
        a = gate.request(reason="a")
        b = gate.request(reason="b")
        assert a.review_id != b.review_id


# ================================================================== 2. 状态流转


class TestTransitions:
    def test_approve(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        approved = gate.approve(rec.review_id, reviewer="human")
        assert approved.status == RG.STATUS_APPROVED
        assert approved.decision == "approved"
        assert approved.reviewer == "human"
        assert approved.reviewed_at

    def test_reject(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        rejected = gate.reject(rec.review_id, reviewer="human")
        assert rejected.status == RG.STATUS_REJECTED
        assert rejected.decision == "rejected"

    def test_cancel(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        cancelled = gate.cancel(rec.review_id)
        assert cancelled.status == RG.STATUS_CANCELLED
        assert cancelled.decision == "cancelled"

    def test_approve_persisted(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        gate.approve(rec.review_id, reviewer="human")
        loaded = gate.load()
        assert loaded[0]["status"] == "approved"
        assert loaded[0]["reviewer"] == "human"

    def test_unknown_id_returns_none(self, tmp_path):
        gate = _gate(tmp_path)
        assert gate.approve("nope", "human") is None
        assert gate.reject("nope", "human") is None
        assert gate.cancel("nope") is None

    def test_double_approve_idempotent(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        gate.approve(rec.review_id, reviewer="h1")
        again = gate.approve(rec.review_id, reviewer="h2")
        assert again.status == "approved"
        assert again.reviewer == "h2"

    def test_status_constants(self):
        assert RG.STATUS_OPEN == "open"
        assert RG.STATUS_APPROVED == "approved"
        assert RG.STATUS_REJECTED == "rejected"
        assert RG.STATUS_CANCELLED == "cancelled"

    def test_review_record_roundtrip(self):
        rec = RG.ReviewRecord(
            review_id="x1", reason="r", trigger="t", status="open",
            context={"project_id": "p1"}, affected_tasks=["T1"],
        )
        assert RG.ReviewRecord.from_dict(rec.to_dict()) == rec

    def test_from_dict_missing_keys_defaults(self):
        rec = RG.ReviewRecord.from_dict({})
        assert rec.status == "open"
        assert rec.risk == "medium"
        assert rec.affected_tasks == []

    def test_from_dict_invalid_status_normalized(self):
        rec = RG.ReviewRecord.from_dict({"status": "weird"})
        assert rec.status == "open"


# ================================================================== 3. pending / status


class TestPendingStatus:
    def test_pending_returns_open_only(self, tmp_path):
        gate = _gate(tmp_path)
        r1 = gate.request(reason="a")
        r2 = gate.request(reason="b")
        gate.approve(r1.review_id, reviewer="h")
        pending = gate.pending()
        assert len(pending) == 1
        assert pending[0].review_id == r2.review_id

    def test_status_none_empty(self, tmp_path):
        assert _gate(tmp_path).status() == "none"

    def test_status_waiting_when_open(self, tmp_path):
        gate = _gate(tmp_path)
        gate.request(reason="r")
        assert gate.status() == "waiting"

    def test_status_approved_after_approve(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        gate.approve(rec.review_id, reviewer="h")
        assert gate.status() == "approved"

    def test_status_rejected_after_reject(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        gate.reject(rec.review_id, reviewer="h")
        assert gate.status() == "rejected"

    def test_status_none_after_cancel(self, tmp_path):
        gate = _gate(tmp_path)
        rec = gate.request(reason="r")
        gate.cancel(rec.review_id)
        assert gate.status() == "none"

    def test_status_project_filter(self, tmp_path):
        gate = _gate(tmp_path)
        gate.request(reason="r", project_id="p1")
        assert gate.status("p1") == "waiting"
        assert gate.status("p2") == "none"

    def test_status_any_open_wins(self, tmp_path):
        # 即使最近已批准, 存在 open → waiting
        gate = _gate(tmp_path)
        r1 = gate.request(reason="a")
        gate.approve(r1.review_id, reviewer="h")
        gate.request(reason="b")
        assert gate.status() == "waiting"

    def test_all_records(self, tmp_path):
        gate = _gate(tmp_path)
        gate.request(reason="a")
        gate.request(reason="b")
        assert len(gate.all_records()) == 2


# ================================================================== 4. 持久化 / 失败安全


class TestPersistence:
    def test_load_after_reopen(self, tmp_path):
        path = tmp_path / "review_records.json"
        gate = RG.ReviewGate(file=path)
        rec = gate.request(reason="r", project_id="p1")
        gate.approve(rec.review_id, reviewer="h")
        gate2 = RG.ReviewGate(file=path)
        assert gate2.status("p1") == "approved"

    def test_load_missing_file_empty(self, tmp_path):
        assert _gate(tmp_path).load() == []

    def test_load_corrupt_file_empty(self, tmp_path):
        path = tmp_path / "review_records.json"
        path.write_text("{bad", encoding="utf-8")
        assert _gate(tmp_path).load() == []

    def test_for_project_uses_project_dir(self, tmp_path):
        gate = RG.ReviewGate.for_project(tmp_path)
        gate.request(reason="r")
        assert (tmp_path / "review_records.json").exists()

    def test_save_failure_safe(self, tmp_path):
        gate = _gate(tmp_path)
        gate.request(reason="r")
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        gate._file = blocker / "review_records.json"
        gate.save(gate.load())  # 不抛
