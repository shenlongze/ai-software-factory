"""tests/intelligence/test_intelligence_decision_cli.py — Intelligence Decision CLI
(Phase 10A-2, ADR-0031): factory intelligence decision create。

覆盖:
- create 冒烟: 文本输出 / --json 结构 / 事件链 / 落库 (decisions.json)
- 输入校验: 禁无证据 rc 1 / 选项格式 rc 2 / 证据格式 rc 2 / context 文件缺失 rc 7 /
  context 文件非法 JSON rc 1 / context JSON 基座 + CLI 覆盖与追加
- 风险规则经 CLI: provider_selection → high + requires_approval; 约束关键词 → high
- Approval 绑定 (9c 真实 ProductService 复用): --approval-artifact --gate →
  approval_request_id 回填 + product store 可见 pending 请求
- Removal Isolation: 模拟删 intelligence 包 → 其它命令零影响 (rc 0),
  intelligence decision create 响亮 rc 1, CLI 模块加载零影响

basename 全仓库唯一 (test_intelligence_* 前缀)。
"""

from __future__ import annotations

import builtins
import json

import pytest

from events.store import EventStore

from intelligence.store import DecisionStore


def _run(root, *argv) -> int:
    from cli.main import main

    return main(["--root", str(root), *argv])


def _base_argv():
    return [
        "intelligence", "decision", "create",
        "--type", "general",
        "--subject", "task-1",
        "--option", "a:0.9:fast and reliable",
        "--option", "b:0.4:cheap but slow",
        "--evidence", "event:exec-1",
        "--evidence", "artifact:bench-1",
    ]


def _create_ok(root, capsys, extra=()):
    rc = _run(root, *_base_argv(), *extra)
    out = capsys.readouterr().out
    return rc, out


# ------------------------------------------------------------------- 冒烟


class TestDecisionCreateSmoke:
    def test_rc0_and_text_output(self, tmp_path, capsys):
        rc, out = _create_ok(tmp_path, capsys)
        assert rc == 0
        assert "✔ 决策" in out
        assert "推荐        a" in out
        assert "备选        b" in out
        assert "置信度" in out
        assert "风险" in out
        assert "intelligence.decision.created seq=" in out

    def test_json_output_structure(self, tmp_path, capsys):
        rc, out = _create_ok(tmp_path, capsys, ("--json",))
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert "event_seq" in data
        d, res = data["decision"], data["result"]
        assert d["decision_type"] == "general"
        assert d["subject_id"] == "task-1"
        assert d["status"] == "recommended"
        assert res["recommendation"] == "a"
        assert res["alternatives"] == ["b"]
        assert 0.0 <= res["confidence"] <= 1.0
        assert res["risk_level"] in ("low", "medium", "high")
        assert "approval_request_id" in res

    def test_decision_carries_options_and_reasoning(self, tmp_path, capsys):
        _, out = _create_ok(tmp_path, capsys, ("--json",))
        d = json.loads(out)["decision"]
        assert len(d["options"]) == 2
        for opt in d["options"]:
            assert opt["score"] > 0
            assert opt["reasoning"]

    def test_decision_persisted_to_store(self, tmp_path, capsys):
        _create_ok(tmp_path, capsys)
        store = DecisionStore(tmp_path / "intelligence")
        assert store.count() == 1
        d = store.list_all()[0]
        assert d.recommendation == "a"

    def test_event_chain_written(self, tmp_path, capsys):
        _create_ok(tmp_path, capsys)
        db = EventStore(tmp_path / "factory.db")
        try:
            types = [e.type.value for e in db.query()]
        finally:
            db.close()
        assert types == [
            "intelligence.decision.analysis.started",
            "intelligence.decision.analysis.completed",
            "intelligence.decision.option.evaluated",
            "intelligence.decision.option.evaluated",
            "intelligence.decision.created",
        ]

    def test_created_event_payload_anchor(self, tmp_path, capsys):
        rc, out = _create_ok(tmp_path, capsys, ("--json",))
        assert rc == 0
        data = json.loads(out)
        db = EventStore(tmp_path / "factory.db")
        try:
            created = [e for e in db.query() if e.type.value == "intelligence.decision.created"]
        finally:
            db.close()
        assert created[0].seq == data["event_seq"]
        assert created[0].payload["decision_id"] == data["decision"]["id"]


# ------------------------------------------------------------- 输入校验


class TestDecisionCreateValidation:
    def test_no_evidence_rc1(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "a:0.8",
        )
        err = capsys.readouterr().err
        assert rc == 1
        assert "evidence" in err

    def test_malformed_option_rc2(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "orphan",
            "--evidence", "event:e1",
        )
        assert rc == 2
        assert "option must be" in capsys.readouterr().err

    def test_bad_factor_count_rc2(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "a:0.9,0.8",
            "--evidence", "event:e1",
        )
        assert rc == 2
        assert "4 factors" in capsys.readouterr().err

    def test_malformed_evidence_rc2(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "a:0.8",
            "--evidence", "just-id",
        )
        assert rc == 2
        assert "evidence must be" in capsys.readouterr().err

    def test_four_factor_option_accepted(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "alpha:0.9,0.7,0.8,0.6:fast",
            "--option", "beta:0.5,0.9,0.6,0.7:cheap",
            "--evidence", "event:e1",
            "--json",
        )
        assert rc == 0
        d = json.loads(capsys.readouterr().out)["decision"]
        assert d["recommendation"] == "alpha"  # 0.785 > 0.65
        assert d["options"][0]["factors"]["capability"] == 0.9

    def test_context_file_missing_rc7(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "a:0.8",
            "--evidence", "event:e1",
            "--context", str(tmp_path / "nope.json"),
        )
        assert rc == 7

    def test_context_file_invalid_json_rc1(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "a:0.8",
            "--evidence", "event:e1",
            "--context", str(bad),
        )
        assert rc == 1
        assert "invalid context file" in capsys.readouterr().err

    def test_context_file_base_with_cli_overrides(self, tmp_path, capsys):
        ctx = {
            "subject": "from-file",
            "decision_type": "general",
            "objective": "base objective",
            "constraints": ["base constraint"],
            "available_options": [{"id": "x", "name": "X", "score": 0.7}],
            "evidence_sources": [{"source_type": "event", "source_id": "file-ev"}],
        }
        f = tmp_path / "ctx.json"
        f.write_text(json.dumps(ctx), encoding="utf-8")
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general",
            "--subject", "cli-wins",  # 覆盖 subject
            "--option", "y:0.9:from cli",  # 追加
            "--constraint", "cli constraint",  # 追加
            "--evidence", "event:cli-ev",  # 追加
            "--context", str(f),
            "--json",
        )
        assert rc == 0
        d = json.loads(capsys.readouterr().out)["decision"]
        assert d["subject_id"] == "cli-wins"
        assert d["description"] == "base objective"  # Decision.description = objective
        assert len(d["options"]) == 2  # 基座 x + CLI y
        assert d["options"][1]["id"] == "y"
        assert any("cli constraint" in o for o in d["analysis"]["observations"])
        assert len(d["evidence"]) == 2  # file-ev + cli-ev


# ------------------------------------------------------------- 风险规则


class TestRiskRulesViaCli:
    def test_provider_selection_high_risk(self, tmp_path, capsys):
        rc, out = _create_ok(tmp_path, capsys, ("--type", "provider_selection", "--json"))
        assert rc == 0
        d = json.loads(out)["decision"]
        assert d["risk_level"] == "high"
        assert d["requires_approval"] is True
        assert d["risk"] == 0.8

    def test_constraint_high_risk_keyword(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "a:0.9", "--option", "b:0.4",
            "--evidence", "event:e1",
            "--constraint", "no breaking change allowed",
            "--json",
        )
        assert rc == 0
        d = json.loads(capsys.readouterr().out)["decision"]
        assert d["risk_level"] == "high"
        assert d["requires_approval"] is True

    def test_low_risk_no_approval(self, tmp_path, capsys):
        rc, out = _create_ok(tmp_path, capsys, ("--json",))
        assert rc == 0
        d = json.loads(out)["decision"]
        assert d["risk_level"] == "low"
        assert d["requires_approval"] is False
        assert d["approval_request_id"] is None


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
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "provider_selection", "--subject", "task-1",
            "--option", "a:0.9", "--option", "b:0.4",
            "--evidence", "event:e1",
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
            "intelligence", "decision", "create",
            "--type", "provider_selection", "--subject", "task-1",
            "--option", "a:0.9", "--option", "b:0.4",
            "--evidence", "event:e1",
            "--approval-artifact", art,
            "--gate", "prd",
        )
        assert rc == 0
        from product.store import ProductStore

        store = ProductStore(tmp_path / "product")
        reqs = store.list_pending_requests()
        assert len(reqs) == 1
        assert reqs[0].artifact_id == art
        assert reqs[0].status == "pending"

    def test_low_risk_with_artifact_does_not_submit(self, tmp_path, capsys):
        art = _seed_artifact(tmp_path)
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "general", "--subject", "task-1",
            "--option", "a:0.9", "--option", "b:0.4",
            "--evidence", "event:e1",
            "--approval-artifact", art,
            "--gate", "prd",
            "--json",
        )
        assert rc == 0
        d = json.loads(capsys.readouterr().out)["decision"]
        assert d["requires_approval"] is False
        assert d["approval_request_id"] is None

    def test_missing_artifact_rc1(self, tmp_path, capsys):
        rc = _run(
            tmp_path,
            "intelligence", "decision", "create",
            "--type", "provider_selection", "--subject", "task-1",
            "--option", "a:0.9", "--option", "b:0.4",
            "--evidence", "event:e1",
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

    def test_decision_create_rc1_without_intelligence(self, tmp_path, monkeypatch, capsys):
        """删包后 intelligence decision create → 装配点响亮失败 rc 1 (不静默降级)。"""
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
