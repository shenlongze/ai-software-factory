"""tests/intelligence/test_intelligence_recommend_cli.py — Intelligence Recommend CLI
(Phase 10A-3, ADR-0032): factory intelligence recommend。

覆盖:
- 冒烟: rc 0 + 文本输出 (Recommendation score + Reasons 分项 + Risk + 事件锚点)
- --json 结构: recommendation/decision 字段 + event_seq
- 落库: RecommendationStore (推荐 Artifact) + DecisionStore (Decision Artifact)
- 事件链: started → candidate.evaluated×N → explained → created → completed
- 输入校验: 候选格式 rc 2 / 数字 rc 2 / 未知类型 rc 2 / 权重格式 rc 2 / 无候选 rc 1
- 自定义权重 --weights / 过滤 --quality --budget / 全过滤 → top None rc 0
- Approval 绑定 (9c 真实 ProductService 复用): --approval-artifact --gate →
  approval_request_id 回填 + product store 可见 pending 请求; 缺失 Artifact rc 1
- Removal Isolation: 模拟删 intelligence 包 → 其它命令零影响 (rc 0),
  intelligence recommend 响亮 rc 1, CLI 模块加载零影响

basename 全仓库唯一 (test_intelligence_* 前缀)。
"""

from __future__ import annotations

import builtins
import json

from events.store import EventStore

from intelligence.store import DecisionStore, RecommendationStore


def _run(root, *argv) -> int:
    from cli.main import main

    return main(["--root", str(root), *argv])


def _base_argv():
    return [
        "intelligence", "recommend",
        "--task", "development",
        "--capability", "code,reasoning",
        "--candidate", "a:0.9:0.8:0.7:0.6",
        "--candidate", "b:0.6:0.6:0.8:0.5",
    ]


def _recommend_ok(root, capsys, extra=()):
    rc = _run(root, *_base_argv(), *extra)
    out = capsys.readouterr().out
    return rc, out


# ------------------------------------------------------------------- 冒烟


class TestRecommendSmoke:
    def test_rc0_and_text_output(self, tmp_path, capsys):
        rc, out = _recommend_ok(tmp_path, capsys)
        assert rc == 0
        assert "✔ 推荐" in out
        assert "(task: development)" in out
        assert "score 0." in out
        assert "Reasons" in out
        assert "风险" in out
        assert "requires_approval:" in out
        assert "intelligence.recommendation.completed seq=" in out

    def test_text_shows_reasoning_items(self, tmp_path, capsys):
        _, out = _recommend_ok(tmp_path, capsys)
        # 每条解释以符号开头 (+ 正向 / - 负向 / ± 中性)
        reason_lines = [ln for ln in out.splitlines() if ln.strip().startswith(("+", "-", "±"))]
        assert len(reason_lines) >= 4
        assert any(ln.strip().startswith("+") for ln in reason_lines)

    def test_text_shows_risk_reasons(self, tmp_path, capsys):
        _, out = _recommend_ok(tmp_path, capsys)
        assert "    - " in out  # 风险理由缩进列表

    def test_top_candidate_in_text(self, tmp_path, capsys):
        _, out = _recommend_ok(tmp_path, capsys)
        # 能力权重最高: a (cap 0.9) 胜出
        assert "推荐        a  score" in out

    def test_json_structure(self, tmp_path, capsys):
        rc, out = _recommend_ok(tmp_path, capsys, ("--json",))
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert "event_seq" in data
        rec = data["recommendation"]
        assert rec["task_type"] == "development"
        assert rec["top_candidate_id"] == "a"
        assert 0.0 <= rec["score"] <= 1.0
        assert rec["confidence"] >= 0.0
        assert rec["risk_level"] in ("low", "medium", "high")
        assert isinstance(rec["requires_approval"], bool)
        assert len(rec["evaluations"]) == 2
        assert rec["reasoning"]
        assert rec["risk_reasons"]

    def test_json_decision_created(self, tmp_path, capsys):
        rc, out = _recommend_ok(tmp_path, capsys, ("--json",))
        assert rc == 0
        d = json.loads(out)["decision"]
        assert d["decision_type"] == "recommendation"
        assert d["recommendation"] == "a"
        assert d["status"] == "recommended"
        assert len(d["options"]) == 2

    def test_json_reasoning_directions(self, tmp_path, capsys):
        _, out = _recommend_ok(tmp_path, capsys, ("--json",))
        rec = json.loads(out)["recommendation"]
        directions = {item["direction"] for item in rec["reasoning"]}
        assert directions <= {"positive", "negative", "neutral"}
        assert "positive" in directions


# ------------------------------------------------------------------ 持久化 + 事件


class TestPersistenceAndEvents:
    def test_recommendation_artifact_saved(self, tmp_path, capsys):
        _recommend_ok(tmp_path, capsys)
        store = RecommendationStore(tmp_path / "intelligence")
        assert store.count() == 1
        art = store.list_all()[0]
        assert art.target_id == "a"
        assert art.reasoning  # 解释随产物

    def test_decision_artifact_saved(self, tmp_path, capsys):
        _recommend_ok(tmp_path, capsys)
        store = DecisionStore(tmp_path / "intelligence")
        assert store.count() == 1
        d = store.list_all()[0]
        assert d.recommendation == "a"

    def test_event_chain_written(self, tmp_path, capsys):
        _recommend_ok(tmp_path, capsys)
        db = EventStore(tmp_path / "factory.db")
        try:
            types = [e.type.value for e in db.query()]
        finally:
            db.close()
        assert types == [
            "intelligence.recommendation.started",
            "intelligence.recommendation.candidate.evaluated",
            "intelligence.recommendation.candidate.evaluated",
            "intelligence.recommendation.explained",
            "intelligence.recommendation.created",
            "intelligence.recommendation.completed",
        ]

    def test_started_payload_capabilities(self, tmp_path, capsys):
        _recommend_ok(tmp_path, capsys)
        db = EventStore(tmp_path / "factory.db")
        try:
            started = [e for e in db.query() if e.type.value == "intelligence.recommendation.started"]
        finally:
            db.close()
        assert started[0].payload["required_capabilities"] == ["code", "reasoning"]
        assert started[0].payload["candidate_count"] == 2

    def test_completed_payload_anchor(self, tmp_path, capsys):
        rc, out = _recommend_ok(tmp_path, capsys, ("--json",))
        assert rc == 0
        data = json.loads(out)
        db = EventStore(tmp_path / "factory.db")
        try:
            completed = [e for e in db.query() if e.type.value == "intelligence.recommendation.completed"]
        finally:
            db.close()
        assert completed[0].payload["top_candidate_id"] == "a"
        assert data["event_seq"] == completed[0].seq


# ------------------------------------------------------------------ 输入校验 (退出码)


class TestInputValidation:
    def test_candidate_too_short_rc2(self, tmp_path, capsys):
        rc = _run(tmp_path, "intelligence", "recommend", "--task", "t", "--candidate", "a:0.9:0.8")
        assert rc == 2
        assert "candidate must be ID:CAP:PERF:COST:EXP" in capsys.readouterr().err

    def test_candidate_bad_number_rc2(self, tmp_path, capsys):
        rc = _run(tmp_path, "intelligence", "recommend", "--task", "t", "--candidate", "a:x:0.8:0.7:0.6")
        assert rc == 2
        assert "factors must be numbers" in capsys.readouterr().err

    def test_candidate_unknown_type_rc2(self, tmp_path, capsys):
        rc = _run(tmp_path, "intelligence", "recommend", "--task", "t", "--candidate", "a:0.9:0.8:0.7:0.6:robot")
        assert rc == 2
        assert "unknown type" in capsys.readouterr().err

    def test_weights_wrong_segments_rc2(self, tmp_path, capsys):
        rc = _run(tmp_path, "intelligence", "recommend", "--task", "t",
                  "--candidate", "a:0.9:0.8:0.7:0.6", "--weights", "1:2:3")
        assert rc == 2
        assert "--weights must be W1:W2:W3:W4" in capsys.readouterr().err

    def test_weights_bad_number_rc2(self, tmp_path, capsys):
        rc = _run(tmp_path, "intelligence", "recommend", "--task", "t",
                  "--candidate", "a:0.9:0.8:0.7:0.6", "--weights", "1:x:3:4")
        assert rc == 2
        assert "--weights must be numbers" in capsys.readouterr().err

    def test_no_candidates_rc1(self, tmp_path, capsys):
        rc = _run(tmp_path, "intelligence", "recommend", "--task", "t")
        assert rc == 1
        assert "no candidates" in capsys.readouterr().err

    def test_missing_task_rc2(self, tmp_path, capsys):
        """缺 --task → argparse SystemExit(2) (入口契约, context 只是基座)。"""
        import pytest

        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, "intelligence", "recommend", "--candidate", "a:0.9:0.8:0.7:0.6")
        assert exc.value.code == 2


# ------------------------------------------------------------------ 权重 / 过滤


class TestWeightsAndFilterCli:
    def test_custom_weights_capability_only(self, tmp_path, capsys):
        """--weights 1:0:0:0 → score = capability (归一化后仍全压能力)。"""
        rc, out = _recommend_ok(tmp_path, capsys, ("--weights", "1:0:0:0", "--json"))
        assert rc == 0
        rec = json.loads(out)["recommendation"]
        assert rec["score"] == 0.9

    def test_quality_filter_excludes_low_capability(self, tmp_path, capsys):
        rc, out = _recommend_ok(tmp_path, capsys, ("--quality", "0.85", "--json"))
        assert rc == 0
        rec = json.loads(out)["recommendation"]
        assert rec["filtered_candidates"] == ["b"]
        assert len(rec["evaluations"]) == 1

    def test_budget_filter_excludes_low_cost_benefit(self, tmp_path, capsys):
        rc, out = _recommend_ok(tmp_path, capsys, ("--budget", "0.75", "--json"))
        assert rc == 0
        rec = json.loads(out)["recommendation"]
        # b cost 0.8 通过, a cost 0.7 < 0.75 → 被过滤 (成本效益不足)
        assert rec["filtered_candidates"] == ["a"]

    def test_all_filtered_no_recommendation_rc0(self, tmp_path, capsys):
        """宁缺毋滥: 全部被过滤 → rc 0 + top None + 高风险 (仍需人工处置)。"""
        rc, out = _recommend_ok(tmp_path, capsys, ("--quality", "0.99", "--json"))
        assert rc == 0
        rec = json.loads(out)["recommendation"]
        assert rec["top_candidate_id"] is None
        assert rec["risk_level"] == "high"
        assert rec["requires_approval"] is True
        assert len(rec["filtered_candidates"]) == 2


# ---------------------------------------------------- Approval 绑定 (9c 复用)


def _seed_artifact(root) -> str:
    """经 9c ProductService 落一个 Artifact (审批绑定点前置条件)。"""
    from product.service import ProductService
    from product.store import ProductStore

    svc = ProductService(ProductStore(root / "product"))
    return svc.create_artifact("prd", {"title": "candidate"}, created_by="test").id


class TestApprovalBindingCli:
    def test_high_risk_with_artifact_submits_9c_request(self, tmp_path, capsys):
        art = _seed_artifact(tmp_path)
        # perf 0.1 → 严重短板 → high 风险
        rc = _run(
            tmp_path,
            "intelligence", "recommend",
            "--task", "development",
            "--candidate", "a:0.9:0.1:0.7:0.6",
            "--approval-artifact", art,
            "--gate", "prd",
            "--json",
        )
        assert rc == 0
        d = json.loads(capsys.readouterr().out)["decision"]
        assert d["requires_approval"] is True
        assert d["approval_request_id"]  # 9c 审批请求已提交

    def test_approval_request_visible_in_product_store(self, tmp_path, capsys):
        art = _seed_artifact(tmp_path)
        rc = _run(
            tmp_path,
            "intelligence", "recommend",
            "--task", "development",
            "--candidate", "a:0.9:0.1:0.7:0.6",
            "--approval-artifact", art,
            "--gate", "prd",
        )
        assert rc == 0
        capsys.readouterr()
        from product.store import ProductStore

        store = ProductStore(tmp_path / "product")
        reqs = store.list_pending_requests()
        assert len(reqs) == 1
        assert reqs[0].artifact_id == art
        assert reqs[0].status == "pending"

    def test_missing_artifact_rc1(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "recommend",
            "--task", "development",
            "--candidate", "a:0.9:0.1:0.7:0.6",
            "--approval-artifact", "ART-NOPE",
            "--gate", "prd",
        )
        assert rc == 1
        assert "approval binding failed" in capsys.readouterr().err


# --------------------------------------------------------- Removal Isolation


class TestRemovalIsolationCli:
    def test_other_commands_unaffected_without_intelligence(self, tmp_path, monkeypatch, capsys):
        """模拟删除 intelligence 包: 其余命令零影响 (agent list rc 0)。"""
        orig = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "intelligence" or name.startswith("intelligence."):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        # 模块加载零影响 (commands/main 顶层零 intelligence imports)
        from cli.main import main  # noqa: F401

        rc = _run(tmp_path, "agent", "list")
        assert rc == 0

    def test_recommend_rc1_without_intelligence(self, tmp_path, monkeypatch, capsys):
        """删包后 intelligence recommend → 装配点响亮失败 rc 1 (不静默降级)。"""
        orig = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "intelligence" or name.startswith("intelligence."):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        rc = _run(tmp_path, *_base_argv())
        assert rc == 1
        assert "intelligence" in capsys.readouterr().err

    def test_no_intelligence_events_on_removal(self, tmp_path, monkeypatch, capsys):
        """删包后 intelligence 命令 rc 1 且零 intelligence.* 事件 (零副作用)。"""
        orig = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "intelligence" or name.startswith("intelligence."):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        _run(tmp_path, *_base_argv())
        capsys.readouterr()
        db = EventStore(tmp_path / "factory.db")
        try:
            types = [e.type.value for e in db.query()]
        finally:
            db.close()
        assert all(not t.startswith("intelligence.") for t in types)
