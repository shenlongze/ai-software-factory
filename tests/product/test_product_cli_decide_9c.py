"""tests/product/test_product_cli_decide_9c.py — CLI 9c 决策/队列/历史/恢复 (Phase 9C, ADR-0028)。

覆盖: decide 四动词 (approve/reject/changes_requested/delegate) + deny 9a 兼容
别名 → REJECTED, --by/--comment 回填, 决定后事件锚点 (approval.rejected 等),
approval list --status 过滤 (approved/rejected/pending/denied 别名归一),
approval history (请求 + 决定联表, artifact 不存在 rc 7, 无请求 count 0),
workflow resume (paused → running + approval.resumed 事件; 未暂停 rc 1;
无工作流 rc 7)。
"""

from __future__ import annotations

import json

from cli_helpers import event_types, open_events, run_cli


def _seed_request(capsys, cli_root, artifact_type: str = "prd") -> str:
    """CLI 链路创建 idea + 申请审批 (返回 request id)。"""
    run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
    run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
    return "APR-001"


class TestDecideVerbs:
    def test_decide_reject(self, capsys, cli_root):
        rid = _seed_request(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "decide", rid, "reject",
            "--comment", "重做",
        )
        assert rc == 0
        assert "REJECTED" in out
        assert "product_decision" not in out  # 非批准不产生 Product Decision
        assert "approval.rejected seq=" in out

    def test_decide_changes_requested(self, capsys, cli_root):
        rid = _seed_request(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "decide", rid, "changes_requested",
            "--comment", "缺竞品分析",
        )
        assert rc == 0
        assert "CHANGES_REQUESTED" in out
        assert "approval.changes_requested seq=" in out

    def test_decide_delegate(self, capsys, cli_root):
        rid = _seed_request(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "decide", rid, "delegate",
            "--by", "lead",
        )
        assert rc == 0
        assert "DELEGATED" in out
        assert "approval.delegated seq=" in out

    def test_decide_deny_alias_maps_rejected(self, capsys, cli_root):
        # 9a 兼容: CLI deny 动词 → 服务层 rejected (状态机语义映射, ADR-0028)
        rid = _seed_request(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "product", "approval", "decide", rid, "deny")
        assert rc == 0
        assert "REJECTED" in out
        assert "approval.rejected seq=" in out

    def test_decide_reject_json_shape(self, capsys, cli_root):
        rid = _seed_request(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "approval", "decide", rid, "reject",
            "--by", "reviewer", "--comment", "no",
        )
        assert rc == 0
        data = json.loads(out)
        assert data["approval"]["status"] == "rejected"
        assert data["approval"]["decided_by"] == "reviewer"
        assert data["approval"]["comment"] == "no"
        assert data["decision"]["decision"] == "rejected"
        assert data["product_decision"] is None

    def test_decide_reject_audits_rejected_event(self, capsys, cli_root):
        rid = _seed_request(capsys, cli_root)
        run_cli(capsys, cli_root, "product", "approval", "decide", rid, "reject")
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "approval.rejected" in types
        assert "approval.granted" not in types

    def test_decide_approve_events_9c_anchor(self, capsys, cli_root):
        # approve 链: 9c 终态事件 + 9a 兼容 granted + resumed 全部落库
        # 顺序: idea → workflow start → approval request (暂停) → decide approve (恢复);
        # 无 workflow 或未暂停 (RUNNING) 都不会发 approval.resumed
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        run_cli(capsys, cli_root, "product", "approval", "decide", "APR-001", "approve")
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "approval.approved" in types
        assert "approval.granted" in types
        assert "approval.resumed" in types


class TestListStatus:
    def _seed_mixed(self, capsys, cli_root):
        """两条审批: APR-001 approved, APR-002 pending。"""
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        run_cli(capsys, cli_root, "product", "approval", "decide", "APR-001", "approve")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-002", "--gate", "prd")

    def test_list_status_approved(self, capsys, cli_root):
        self._seed_mixed(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "list", "--status", "approved"
        )
        assert rc == 0
        assert "1 approvals" in out
        assert "APR-001" in out
        assert "APR-002" not in out

    def test_list_status_rejected_and_denied_alias(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        run_cli(capsys, cli_root, "product", "approval", "decide", "APR-001", "deny")
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "list", "--status", "denied"
        )
        assert rc == 0
        assert "1 approvals" in out  # denied 别名 → rejected 归一
        rc, out2, _ = run_cli(
            capsys, cli_root, "product", "approval", "list", "--status", "rejected"
        )
        assert "APR-001" in out2

    def test_list_status_pending_excludes_terminal(self, capsys, cli_root):
        self._seed_mixed(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "approval", "list", "--status", "pending"
        )
        assert rc == 0
        assert "APR-002" in out
        assert "APR-001" not in out

    def test_list_status_json(self, capsys, cli_root):
        self._seed_mixed(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "approval", "list", "--status", "approved"
        )
        assert rc == 0
        data = json.loads(out)
        assert data["count"] == 1
        assert data["approvals"][0]["id"] == "APR-001"
        assert data["approvals"][0]["status"] == "approved"


class TestHistoryCommand:
    def _seed_history(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        run_cli(capsys, cli_root, "product", "approval", "decide", "APR-001", "approve",
                "--comment", "ok")

    def test_history_joins_decision(self, capsys, cli_root):
        self._seed_history(capsys, cli_root)
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "approval", "history", "ART-001"
        )
        assert rc == 0
        data = json.loads(out)
        assert data["count"] == 1
        row = data["history"][0]
        assert row["id"] == "APR-001"
        assert row["artifact_version"] == 1
        assert row["decision"]["decision"] == "approved"
        assert row["decision"]["comment"] == "ok"

    def test_history_missing_artifact_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(
            capsys, cli_root, "product", "approval", "history", "ART-999"
        )
        assert rc == 7
        assert "artifact not found" in err

    def test_history_no_requests_count_zero(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "approval", "history", "ART-001"
        )
        assert rc == 0
        data = json.loads(out)
        assert data["count"] == 0
        assert data["history"] == []

    def test_history_audits_approval_viewed(self, capsys, cli_root):
        self._seed_history(capsys, cli_root)
        run_cli(capsys, cli_root, "product", "approval", "history", "ART-001")
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "approval.viewed" in types


class TestWorkflowResumeCommand:
    def test_resume_paused_to_running(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "workflow", "resume", "PI-001"
        )
        assert rc == 0
        data = json.loads(out)
        assert data["workflow"]["status"] == "running"
        assert data["workflow"]["current_stage"] == "research"  # 停留当前 stage
        assert data["event_seq"]  # approval.resumed seq (--json 输出无文本锚点, 以 event_seq 字段为准)

    def test_resume_not_paused_rc1(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        rc, out, err = run_cli(capsys, cli_root, "product", "workflow", "resume", "PI-001")
        assert rc == 1
        assert "not paused" in err

    def test_resume_missing_workflow_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "product", "workflow", "resume", "PI-999")
        assert rc == 7
        assert "no product workflow" in err

    def test_resume_audits_resumed_event(self, capsys, cli_root):
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        run_cli(capsys, cli_root, "product", "workflow", "start", "PI-001")
        run_cli(capsys, cli_root, "product", "approval", "request", "ART-001", "--gate", "prd")
        run_cli(capsys, cli_root, "product", "workflow", "resume", "PI-001")
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "approval.resumed" in types
