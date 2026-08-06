"""tests/product/test_product_lifecycle_cli_9d.py — CLI lifecycle 4 命令 + 退出码 (Phase 9d, ADR-0029)。

覆盖: lifecycle start (rc 0/审计/JSON/idea 缺失 rc 7/重复 rc 1/模板缺失 rc 7),
lifecycle status (rc 0 快照输出/无生命周期 rc 7/审计 status_viewed),
lifecycle advance (rc 0 推进/缺产物 rc 1/approval 阶段 rc 1/无生命周期 rc 7),
lifecycle templates (rc 0 模板表/审计 templates_viewed), parser 子命令注册,
CLI 全链端到端: idea → start → advance → approval 暂停 → decide approve →
生命周期自动推进 (decide 联动 handle_approval_outcome)。
"""

from __future__ import annotations

import json

import pytest

from cli.main import build_parser
from events.models import EventType

from cli_helpers import event_types, open_events, run_cli
from product_helpers import make_service, make_store, seed_artifact


def _cli_service(root):
    """与 CLI 同一 product 数据空间的 ProductService (测试内造产物)。"""
    return make_service(root / "product")


class TestParser:
    def test_lifecycle_subcommands_registered(self):
        p = build_parser()
        for sub in ("start", "status", "advance", "templates"):
            args = p.parse_args(["product", "lifecycle", sub, "PI-001"] if sub != "templates" else ["product", "lifecycle", sub])
            assert args.product_command == "lifecycle"
            assert args.lifecycle_command == sub

    def test_lifecycle_start_accepts_template(self):
        p = build_parser()
        args = p.parse_args(["product", "lifecycle", "start", "PI-001", "--template", "software_project"])
        assert args.template == "software_project"


class TestStartCommand:
    def _seed_idea(self, capsys, cli_root) -> str:
        rc, out, err = run_cli(capsys, cli_root, "--json", "product", "idea", "create", "--title", "CLI 生命周期")
        assert rc == 0
        return json.loads(out)["idea"]["id"]

    def test_start_ok_and_audit(self, capsys, cli_root):
        idea_id = self._seed_idea(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)
        assert rc == 0, err
        assert "LC-001" in out
        assert "running" in out
        with open_events(cli_root) as store:
            types = event_types(store)
            assert EventType.PRODUCT_LIFECYCLE_STARTED.value in types
            assert EventType.PRODUCT_STAGE_ENTERED.value in types

    def test_start_json(self, capsys, cli_root):
        idea_id = self._seed_idea(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "start", idea_id)
        assert rc == 0
        data = json.loads(out)
        assert data["lifecycle"]["id"] == "LC-001"
        assert data["current_stage"]["name"] == "idea"
        assert data["ok"] is True

    def test_start_missing_idea_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "start", "PI-999")
        assert rc == 7
        assert "idea not found" in err

    def test_start_duplicate_rc1(self, capsys, cli_root):
        idea_id = self._seed_idea(capsys, cli_root)
        run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)
        assert rc == 1
        assert "already started" in err

    def test_start_unknown_template_rc7(self, capsys, cli_root):
        idea_id = self._seed_idea(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "start",
                               idea_id, "--template", "nope")
        assert rc == 7
        assert "no lifecycle template" in err


class TestTemplatesCommand:
    def test_templates_ok(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "templates")
        assert rc == 0, err
        assert "software_project" in out
        assert "1 lifecycle templates" in out

    def test_templates_json_and_audit(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "templates")
        assert rc == 0
        data = json.loads(out)
        assert data["count"] == 1
        assert data["templates"][0]["name"] == "software_project"
        assert len(data["templates"][0]["stages"]) == 8
        with open_events(cli_root) as store:
            assert EventType.PRODUCT_LIFECYCLE_TEMPLATES_VIEWED.value in event_types(store)


class TestStatusCommand:
    def _started(self, capsys, cli_root) -> str:
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "idea", "create", "--title", "状态")
        idea_id = json.loads(out)["idea"]["id"]
        rc, out, _ = run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)
        return idea_id

    def test_status_ok(self, capsys, cli_root):
        idea_id = self._started(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "status", idea_id)
        assert rc == 0, err
        assert "LC-001" in out
        assert "current_stage idea" in out
        assert "下一步" in out
        assert "generate product_idea artifact" in out

    def test_status_json_shape(self, capsys, cli_root):
        idea_id = self._started(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "status", idea_id)
        assert rc == 0
        data = json.loads(out)
        assert data["current_stage"]["name"] == "idea"
        assert data["pending_approval"] is None
        assert isinstance(data["artifacts"], list)
        assert isinstance(data["decisions"], list)
        assert isinstance(data["next_actions"], list)

    def test_status_missing_lifecycle_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "status", "PI-999")
        assert rc == 7
        assert "no product lifecycle" in err

    def test_status_audit_event(self, capsys, cli_root):
        idea_id = self._started(capsys, cli_root)
        run_cli(capsys, cli_root, "product", "lifecycle", "status", idea_id)
        with open_events(cli_root) as store:
            assert EventType.PRODUCT_LIFECYCLE_STATUS_VIEWED.value in event_types(store)


class TestAdvanceCommand:
    def _to_research(self, capsys, cli_root) -> str:
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "idea", "create", "--title", "推进")
        idea_id = json.loads(out)["idea"]["id"]
        run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)
        return idea_id

    def test_advance_ok(self, capsys, cli_root):
        idea_id = self._to_research(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)
        assert rc == 0, err
        assert "current_stage research" in out
        assert "product.stage.completed" in out

    def test_advance_missing_artifact_rc1(self, capsys, cli_root):
        idea_id = self._to_research(capsys, cli_root)
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)  # idea→research
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)
        assert rc == 1
        assert "needs a 'research' artifact" in err

    def test_advance_missing_lifecycle_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "advance", "PI-999")
        assert rc == 7

    def test_advance_approval_stage_rc1(self, capsys, cli_root):
        idea_id = self._to_research(capsys, cli_root)
        svc = _cli_service(cli_root)
        seed_artifact(svc, "research", idea_id=idea_id)
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)  # idea→research
        seed_artifact(svc, "prd", idea_id=idea_id)
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)  # research→prd
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)  # prd→approval (paused)
        rc, out, err = run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)
        assert rc == 1
        assert "advance via approval" in err


class TestDecideLinkageEndToEnd:
    def test_full_cli_chain_approval_decide_advances(self, capsys, cli_root):
        """CLI 全链: start → advance×3 → approval 暂停 → decide approve →
        生命周期自动推进到 ui (decide 挂接 handle_approval_outcome)。"""
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "idea", "create", "--title", "端到端")
        idea_id = json.loads(out)["idea"]["id"]
        assert run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)[0] == 0
        assert run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)[0] == 0  # idea→research
        svc = _cli_service(cli_root)
        seed_artifact(svc, "research", idea_id=idea_id)
        assert run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)[0] == 0  # research→prd
        seed_artifact(svc, "prd", idea_id=idea_id)
        assert run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)[0] == 0  # prd→approval
        # approval 暂停 + pending 请求存在
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "status", idea_id)
        status = json.loads(out)
        assert status["lifecycle"]["status"] == "paused"
        assert status["pending_approval"]["status"] == "pending"
        request_id = status["pending_approval"]["id"]
        # decide approve → 生命周期联动推进 (approval 完成 → ui 进入)
        rc, out, err = run_cli(capsys, cli_root, "--json", "product", "approval", "decide",
                               request_id, "approve", "--by", "pm")
        assert rc == 0, err
        data = json.loads(out)
        assert data["lifecycle"] is not None
        assert data["lifecycle"]["status"] == "running"
        assert data["lifecycle"]["current_stage"]["name"] == "ui"
        # 审计: decide 终态事件 + 生命周期阶段完成事件
        with open_events(cli_root) as store:
            types = event_types(store)
            assert EventType.APPROVAL_APPROVED.value in types
            assert EventType.PRODUCT_STAGE_COMPLETED.value in types

    def test_full_cli_chain_reject_stays_paused(self, capsys, cli_root):
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "idea", "create", "--title", "拒绝")
        idea_id = json.loads(out)["idea"]["id"]
        run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)
        svc = _cli_service(cli_root)
        for artifact_type in ("research", "prd"):
            seed_artifact(svc, artifact_type, idea_id=idea_id)
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)  # → approval paused
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "status", idea_id)
        request_id = json.loads(out)["pending_approval"]["id"]
        rc, out, err = run_cli(capsys, cli_root, "--json", "product", "approval", "decide",
                               request_id, "reject", "--comment", "重做")
        assert rc == 0, err
        data = json.loads(out)
        assert data["lifecycle"]["status"] == "paused"  # 非批准终态 → 停留
        assert data["lifecycle"]["current_stage"]["name"] == "approval"

    def test_full_chain_status_shows_decision_stage_after_second_approve(self, capsys, cli_root):
        """二次审批通过 → architecture (decision) 阶段进入 (决策链中段)。"""
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "idea", "create", "--title", "架构")
        idea_id = json.loads(out)["idea"]["id"]
        run_cli(capsys, cli_root, "product", "lifecycle", "start", idea_id)
        svc = _cli_service(cli_root)
        for artifact_type in ("research", "prd", "ui"):
            seed_artifact(svc, artifact_type, idea_id=idea_id)
        for _ in range(3):
            run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "status", idea_id)
        r1 = json.loads(out)["pending_approval"]["id"]
        run_cli(capsys, cli_root, "product", "approval", "decide", r1, "approve")
        run_cli(capsys, cli_root, "product", "lifecycle", "advance", idea_id)  # ui→approval(ui)
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "status", idea_id)
        r2 = json.loads(out)["pending_approval"]["id"]
        run_cli(capsys, cli_root, "product", "approval", "decide", r2, "approve")
        rc, out, _ = run_cli(capsys, cli_root, "--json", "product", "lifecycle", "status", idea_id)
        status = json.loads(out)
        assert status["lifecycle"]["status"] == "running"
        assert status["current_stage"]["name"] == "architecture"
        assert status["current_stage"]["kind"] == "decision"
