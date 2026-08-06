"""tests/product/test_product_cli.py — factory product CLI: idea/approval/workflow (Phase 9A, ADR-0026)。

覆盖: idea create/list/show (+--json + 事件审计), approval request (默认门/无门 rc 1/
显式 --gate/未找到 rc 7), approval decide approve|deny (CLI 动词 → 服务层终态值,
granted 产生 Product Decision), approval list --pending, workflow start/status
(+未找到 rc 7 / 重复启动 rc 1), 未知子命令 rc 2, 用法错误 SystemExit(2),
--json 出口形状, 完整链路事件序 (idea.created → approval.required →
approval.granted → product.workflow.started)。
"""

from __future__ import annotations

import json

import pytest

from cli_helpers import event_types, open_events, run_cli
from product_helpers import payload_of


class TestIdeaCommands:
    def test_idea_create(self, capsys, cli_root):
        rc, out, _ = run_cli(capsys, cli_root, "product", "idea", "create", "--title", "AI 助手")
        assert rc == 0
        assert "PI-001" in out
        assert "ART-001" in out
        assert "idea.created seq=" in out

    def test_idea_create_json(self, capsys, cli_root):
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "idea", "create",
            "--title", "AI 助手", "--description", "d", "--goals", "g1,g2",
        )
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["idea"]["id"] == "PI-001"
        assert data["idea"]["goals"] == ["g1", "g2"]
        assert data["artifact"]["type"] == "product_idea"
        assert data["artifact"]["content"]["idea_id"] == "PI-001"
        assert data["event_seq"] == 1

    def test_idea_create_audits_idea_created(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "idea.created" in types
        assert "idea.viewed" not in types

    def test_idea_list(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "a")
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "b")
        rc, out, _ = run_cli(capsys, cli_root, "product", "idea", "list")
        assert rc == 0
        assert "2 ideas" in out
        assert "PI-001" in out and "PI-002" in out

    def test_idea_list_json(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "a")
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "idea", "list")
        assert rc == 0
        data = json.loads(out)
        assert data["count"] == 1
        assert data["ideas"][0]["title"] == "a"

    def test_idea_list_audits_viewed(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "list")
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "idea.viewed" in types

    def test_idea_show(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "a")
        rc, out, _ = run_cli(capsys, cli_root, "product", "idea", "show", "PI-001")
        assert rc == 0
        assert "PI-001" in out
        assert "idea.viewed seq=" in out

    def test_idea_show_missing_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "idea", "show", "PI-999")
        assert rc == 7
        assert "idea not found" in err

    def test_idea_create_missing_title_usage_error(self, cli_root):
        from cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "product", "idea", "create"])
        assert exc.value.code == 2


class TestApprovalCommands:
    def _seed_idea_and_artifact(self, capsys, cli_root) -> None:
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")

    def test_request_default_gate_prd(self, capsys, cli_root, tmp_path):
        # 直接经 CLI 无法创建 prd Artifact → 用服务层 seed (CLI 未暴露 create_artifact)
        from cli.main import main

        from product.service import ProductService
        from product.store import ProductStore

        ProductService(ProductStore(cli_root / "product")).create_artifact("prd")
        rc, out, _ = run_cli(capsys, cli_root, "product", "approval", "request", "ART-001")
        assert rc == 0
        assert "APR-001" in out
        assert "gate: prd" in out
        assert "approval.required seq=" in out

    def test_request_product_idea_no_gate_rc1(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        rc, out, err = run_cli(capsys, cli_root, "product", "approval", "request", "ART-001")
        assert rc == 1
        assert "no approval gate" in err
        assert "product_idea" in err

    def test_request_with_explicit_gate(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd"
        )
        assert rc == 0
        assert "gate: prd" in out
        assert "idea      PI-001" in out  # 从 artifact.content.idea_id 推导

    def test_request_missing_artifact_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "approval", "request", "ART-999")
        assert rc == 7
        assert "artifact not found" in err

    def test_decide_approve(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "decide", "APR-001", "approve",
            "--comment", "ok",
        )
        assert rc == 0
        assert "APPROVED" in out
        assert "product_decision" in out
        assert "approval.granted seq=" in out

    def test_decide_approve_json(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "approval", "decide", "APR-001", "approve"
        )
        assert rc == 0
        data = json.loads(out)
        assert data["approval"]["status"] == "approved"
        assert data["decision"]["decision"] == "approved"
        assert data["product_decision"]["type"] == "product_decision"

    def test_decide_deny(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "decide", "APR-001", "deny",
            "--comment", "重做",
        )
        assert rc == 0
        assert "DENIED" in out
        assert "approval.denied seq=" in out
        assert "product_decision" not in out

    def test_decide_twice_rc1(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        run_cli(capsys, cli_root, "product", "approval", "decide", "APR-001", "approve")
        rc, out, err = run_cli(capsys, cli_root, "product", "approval", "decide", "APR-001", "deny")
        assert rc == 1
        assert "already approved" in err

    def test_decide_missing_request_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "approval", "decide", "APR-999", "approve")
        assert rc == 7
        assert "approval request not found" in err

    def test_decide_invalid_choice_usage_error(self, cli_root):
        from cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "product", "approval", "decide", "APR-001", "maybe"])
        assert exc.value.code == 2

    def test_approval_list_pending(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        rc, out, _ = run_cli(capsys, cli_root, "product", "approval", "list", "--pending")
        assert rc == 0
        assert "1 approvals" in out
        assert "APR-001" in out
        assert "approval.viewed seq=" not in out  # list 打印不显示事件行 (表格式)

    def test_approval_list_audits_viewed(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "approval", "list")
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "approval.viewed" in types


class TestWorkflowCommands:
    def test_workflow_start(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        rc, out, _ = run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        assert rc == 0
        assert "PW-001" in out
        assert "current_stage research" in out
        assert "research → prd → ui → architecture → tasks" in out
        assert "product.workflow.started seq=" in out

    def test_workflow_start_json(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "workflow", "start", "PI-001")
        assert rc == 0
        data = json.loads(out)
        assert data["workflow"]["id"] == "PW-001"
        assert data["workflow"]["current_stage"] == "research"

    def test_workflow_start_missing_idea_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "workflow", "start", "PI-999")
        assert rc == 7
        assert "idea not found" in err

    def test_workflow_start_twice_rc1(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        rc, out, err = run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        assert rc == 1
        assert "already started" in err

    def test_workflow_status(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        rc, out, _ = run_cli(capsys, cli_root, "product", "workflow", "status", "PI-001")
        assert rc == 0
        assert "PW-001" in out
        assert "product.workflow.status_viewed seq=" in out

    def test_workflow_status_json(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "workflow", "status", "PI-001")
        assert rc == 0
        data = json.loads(out)
        assert data["workflow"]["status"] == "running"
        assert data["workflow"]["product_decision"] is None

    def test_workflow_status_missing_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "workflow", "status", "PI-999")
        assert rc == 7
        assert "no product workflow" in err


class TestDispatchAndUsage:
    def test_unknown_product_command_rc2(self, cli_root):
        from cli.main import main

        # argparse 对未知子命令直接 SystemExit(2) (同既有 task/event 模式)
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "product", "bogus"])
        assert exc.value.code == 2

    def test_unknown_idea_command_rc2(self, cli_root):
        from cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "product", "idea", "bogus"])
        assert exc.value.code == 2

    def test_missing_product_subcommand_usage_error(self, cli_root):
        from cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "product"])
        assert exc.value.code == 2


class TestFullChain:
    def test_full_chain_idea_to_workflow(self, capsys, cli_root):
        """idea create → approval request(--gate prd) → decide approve → workflow
        start → status: 完整链路 + 事件序 + 状态机联动。"""
        assert run_cli(capsys, cli_root, "product", "idea", "create", "--title", "AI 助手")[0] == 0
        assert run_cli(
            capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd"
        )[0] == 0
        assert run_cli(
            capsys, cli_root, "product", "approval", "decide", "APR-001", "approve"
        )[0] == 0
        assert run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")[0] == 0
        rc, out, _ = run_cli(capsys, cli_root, "product", "workflow", "status", "PI-001")
        assert rc == 0
        assert "current_stage research" in out  # workflow 在 approval 前启动才会推进

    def test_full_chain_events(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        run_cli(capsys, cli_root, "product", "approval", "decide", "APR-001", "approve")
        store = open_events(cli_root)
        types = event_types(store)
        assert "idea.created" in types
        assert "approval.required" in types
        assert "approval.granted" in types
        payload = payload_of(store, "approval.granted")
        store.close()
        assert payload["decision"] == "approved"
        assert payload["artifact_type"] == "product_idea"

    def test_workflow_pauses_and_resumes_via_cli(self, capsys, cli_root):
        """workflow start → approval request → status awaiting_approval →
        decide approve → status running + stage 推进 + product_decision。"""
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "workflow", "status", "PI-001")
        assert json.loads(out)["workflow"]["status"] == "awaiting_approval"
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "approval", "decide", "APR-001", "approve"
        )
        pd = json.loads(out)["product_decision"]["id"]
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "workflow", "status", "PI-001")
        wf = json.loads(out)["workflow"]
        assert wf["status"] == "running"
        assert wf["current_stage"] == "prd"
        assert wf["product_decision"] == pd
