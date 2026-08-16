"""S10-065 — Review UX 测试套件 (Batch B)。

覆盖: ReviewView (from_review/to_markdown/options) + review_view/approve/reject/cancel action。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ACT = import_module("factory-console.session.actions")
RV = import_module("factory-console.session.review_view")
RG = import_module("factory-console.session.review_gate")


def _gate(ws: Path) -> RG.ReviewGate:
    return RG.ReviewGate(file=ws / "cost" / "review_records.json")


def _ws(tmp_path) -> Path:
    ws = tmp_path / "ws"
    (ws / "cost").mkdir(parents=True, exist_ok=True)
    (ws / "projects").mkdir(exist_ok=True)
    return ws


class TestReviewView:
    def test_from_review(self, tmp_path):
        ws = _ws(tmp_path)
        gate = _gate(ws)
        rec = gate.request(reason="预算 90%", trigger="budget_review",
                           context={"project_id": "p"}, affected_tasks=["T1"],
                           estimated_cost=0.9, risk="high")
        view = RV.ReviewView.from_review(rec, context={"current_cost": 0.9})
        assert view.review_id == rec.review_id
        assert view.reason == "预算 90%"
        assert view.risk == "high"
        assert view.current_cost == 0.9

    def test_options(self, tmp_path):
        ws = _ws(tmp_path)
        gate = _gate(ws)
        rec = gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                           estimated_cost=0, risk="low")
        view = RV.ReviewView.from_review(rec)
        assert view.options == ["APPROVE", "REJECT", "CANCEL"]

    def test_to_markdown(self, tmp_path):
        ws = _ws(tmp_path)
        gate = _gate(ws)
        rec = gate.request(reason="预算已使用 90%", trigger="budget_review",
                           context={"project_id": "p"}, affected_tasks=["T1"],
                           estimated_cost=0.9, risk="high")
        view = RV.ReviewView.from_review(rec)
        md = view.to_markdown()
        assert "AI Factory" in md or "确认" in md
        assert "预算已使用 90%" in md
        assert "继续" in md or "APPROVE" in md

    def test_from_review_defaults(self, tmp_path):
        """缺失字段 → 缺省占位 (失败安全)。"""
        ws = _ws(tmp_path)
        gate = _gate(ws)
        rec = gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                           estimated_cost=0, risk="low")
        view = RV.ReviewView.from_review(rec)
        assert view.current_agent == "" or view.current_agent is not None

    def test_to_dict(self, tmp_path):
        ws = _ws(tmp_path)
        gate = _gate(ws)
        rec = gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                           estimated_cost=0, risk="low")
        d = RV.ReviewView.from_review(rec).to_dict()
        assert "review_id" in d
        assert "options" in d


class TestReviewActions:
    def test_review_view_no_pending(self, tmp_path):
        ws = _ws(tmp_path)
        r = ACT.review_view(_ctx(ws))
        assert r.ok
        assert "无需人工评审" in r.message

    def test_review_view_pending_list(self, tmp_path):
        ws = _ws(tmp_path)
        _gate(ws).request(reason="需要确认", trigger="budget", context={},
                          affected_tasks=[], estimated_cost=0, risk="low")
        r = ACT.review_view(_ctx(ws))
        assert r.ok
        assert "需要确认" in r.message

    def test_review_view_detail(self, tmp_path):
        ws = _ws(tmp_path)
        rec = _gate(ws).request(reason="预算 90%", trigger="budget",
                                context={}, affected_tasks=[], estimated_cost=0,
                                risk="high")
        r = ACT.review_view(_ctx(ws, {"review_id": rec.review_id}))
        assert r.ok
        assert "预算 90%" in r.message

    def test_review_approve(self, tmp_path):
        ws = _ws(tmp_path)
        rec = _gate(ws).request(reason="r", trigger="t", context={},
                                affected_tasks=[], estimated_cost=0, risk="low")
        r = ACT.review_approve(_ctx(ws, {"review_id": rec.review_id}))
        assert r.ok
        assert "approved" in r.message or "批准" in r.message

    def test_review_approve_single_pending(self, tmp_path):
        """单待审 → 直接批准 (无需 review_id)。"""
        ws = _ws(tmp_path)
        _gate(ws).request(reason="r", trigger="t", context={}, affected_tasks=[],
                          estimated_cost=0, risk="low")
        r = ACT.review_approve(_ctx(ws))
        assert r.ok

    def test_review_reject(self, tmp_path):
        ws = _ws(tmp_path)
        rec = _gate(ws).request(reason="r", trigger="t", context={},
                                affected_tasks=[], estimated_cost=0, risk="high")
        r = ACT.review_reject(_ctx(ws, {"review_id": rec.review_id}))
        assert r.ok
        assert "rejected" in r.message or "拒绝" in r.message

    def test_review_cancel(self, tmp_path):
        ws = _ws(tmp_path)
        rec = _gate(ws).request(reason="r", trigger="t", context={},
                                affected_tasks=[], estimated_cost=0, risk="low")
        r = ACT.review_cancel(_ctx(ws, {"review_id": rec.review_id}))
        assert r.ok
        assert "cancelled" in r.message or "取消" in r.message

    def test_approve_no_pending(self, tmp_path):
        ws = _ws(tmp_path)
        r = ACT.review_approve(_ctx(ws))
        assert r.ok  # 失败安全

    def test_review_corrupt_file(self, tmp_path):
        ws = _ws(tmp_path)
        (ws / "cost" / "review_records.json").write_text("bad json", encoding="utf-8")
        r = ACT.review_view(_ctx(ws))
        assert r.ok  # 失败安全


def _ctx(ws: Path, params: dict | None = None):
    class FakeContext:
        def __init__(self, workspace, params):
            self.workspace = str(workspace)
            self.params = params or {}
            self.project = ""

        def require(self, level):
            pass

    return FakeContext(ws, params)
