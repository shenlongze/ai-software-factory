"""S17: Workforce Governance & Human Approval。

覆盖:
- Governance Contract / Policy
- ApprovalRequest (PENDING→APPROVED/REJECTED, append-only)
- Agent 不能 self-approve
- Approval 绑定 immutable Artifact (staleness)
- Governance Gate (check: allowed/missing/reason)
- Release Gate (verification+evaluation+approval)
- No fake approval (无 approval → BLOCKED; 伪造 id → DENIED)
- Idempotency (重复 approve/reject 拒绝)
- CLI / API
- Real Approve E2E (approval → release allowed)
- Real Reject E2E (reject → release BLOCKED)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.governance_service import (  # noqa: E402
    request_approval, approve, reject, get_approval, list_approvals,
    check_governance, release, POLICIES,
)
from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run, get_production_run,
    _write,
)
from factory_console.node_runtime import (  # noqa: E402
    register_node, create_node_run, execute_node_run,
)


def _completed_run(tmp_path) -> tuple[str, list[str]]:
    """COMPLETED ProductionRun with artifact。返回 (run_id, artifact_ids)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
    register_node(str(tmp_path), node_id="a", name="A", node_type="engineering")

    def factory(node_id):
        def fn(input_data):
            patch = (f"diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                     "@@ -0,0 +1,2 @@\n+def a():\n+    return 1\n")
            return {"ok": True, "output": {"code": "a"}, "patch_text": patch,
                    "artifact_type": "code_change",
                    "verification": {"result": "PASS"}}
        return fn
    done = execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                                  artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    prun = get_production_run(str(tmp_path), run["run_id"])
    return run["run_id"], list(prun.get("artifacts", []))


# --- Governance Contract / Policy ---

def test_policy_contract(tmp_path):
    assert "code_generation" in POLICIES
    assert POLICIES["code_generation"]["approval_required"] is False
    assert POLICIES["release"]["approval_required"] is True
    assert POLICIES["release"]["risk_level"] == "high"
    assert POLICIES["production_apply"]["approval_required"] is True


# --- Approval lifecycle + append-only ---

def test_approval_lifecycle(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="developer-agent")
    assert a["decision"] == "PENDING"
    assert len(a["history"]) == 1
    a2 = approve(str(tmp_path), a["approval_id"], decided_by="human", reason="ok")
    assert a2["decision"] == "APPROVED"
    assert a2["decided_by"] == "human"
    assert len(a2["history"]) == 2
    # append-only: 历史不可改
    assert a2["history"][0]["to"] == "PENDING"
    assert a2["history"][1]["to"] == "APPROVED"


# --- Agent 不能 self-approve ---

def test_self_approve_denied(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="developer-agent")
    with pytest.raises(PermissionError):
        approve(str(tmp_path), a["approval_id"], decided_by="developer-agent")


# --- Agent 不能 approve (只有 human) ---

def test_agent_approve_denied(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="dev-agent")
    with pytest.raises(PermissionError):
        approve(str(tmp_path), a["approval_id"], decided_by="qa_agent")


# --- 伪造 approval → DENIED ---

def test_fake_approval_denied(tmp_path):
    rid, arts = _completed_run(tmp_path)
    with pytest.raises(ValueError):
        approve(str(tmp_path), "appr-fake-123", decided_by="human")


# --- Idempotency: 重复 approve/reject ---

def test_approval_idempotency(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    with pytest.raises(ValueError):
        approve(str(tmp_path), a["approval_id"], decided_by="human")  # 已决
    with pytest.raises(ValueError):
        reject(str(tmp_path), a["approval_id"], decided_by="human")  # 非法转换


# --- Governance Gate: 无 approval → BLOCKED ---

def test_gate_no_approval_blocked(tmp_path):
    rid, arts = _completed_run(tmp_path)
    g = check_governance(str(tmp_path), rid, action="release")
    assert g["allowed"] is False
    assert "approval" in g["missing"]
    assert g["reason"]  # 必须解释为什么


# --- Approval 绑定 Artifact (staleness) ---

def test_approval_stale_blocks_release(tmp_path):
    """Approval(A) 不授权 Artifact B (staleness)。"""
    rid, arts = _completed_run(tmp_path)
    from factory_console.production_evaluation import evaluate as _ev
    _ev(str(tmp_path), rid)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    # 匹配的 approval → release allowed
    r = release(str(tmp_path), rid, approval_id=a["approval_id"])
    assert r["allowed"] is True, r
    # stale: 来自其他 run 的 approval (不同 artifact 集合) → BLOCKED
    rid2, arts2 = _completed_run(tmp_path)
    a2 = request_approval(str(tmp_path), production_run_id=rid2,
                          artifact_ids=arts2, requested_by="dev-agent")
    approve(str(tmp_path), a2["approval_id"], decided_by="human")
    r2 = release(str(tmp_path), rid, approval_id=a2["approval_id"])
    assert r2["allowed"] is False
    assert "approval_stale" in r2["missing"] or "approval" in r2["missing"]


# --- Release Gate 全条件 ---

def test_release_gate_requires_all(tmp_path):
    rid, arts = _completed_run(tmp_path)
    # 无 approval → BLOCKED
    r = release(str(tmp_path), rid)
    assert r["allowed"] is False
    assert "approval" in r["missing"]
    # 有 approval → allowed (verification COMPLETED + evaluation + approval)
    from factory_console.production_evaluation import evaluate as _ev
    _ev(str(tmp_path), rid)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    r2 = release(str(tmp_path), rid, approval_id=a["approval_id"])
    assert r2["allowed"] is True, r2
    assert r2["missing"] == []


# --- Reject path ---

def test_reject_blocks_release(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="dev-agent")
    reject(str(tmp_path), a["approval_id"], decided_by="human", reason="not ready")
    assert get_approval(str(tmp_path), a["approval_id"])["decision"] == "REJECTED"
    r = release(str(tmp_path), rid, approval_id=a["approval_id"])
    assert r["allowed"] is False
    assert "approval" in r["missing"]


# --- CLI ---

def test_cli_governance(tmp_path):
    rid, arts = _completed_run(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["governance", "check", rid, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["approval-request", "request", rid, "--artifact", ",".join(arts),
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["approval-request", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["governance", "status", rid, "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_governance(tmp_path):
    rid, arts = _completed_run(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    # governance check
    resp = client.get(f"/api/production-runs/{rid}/governance", params={"action": "release"})
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
    # request approval
    resp = client.post(f"/api/production-runs/{rid}/approval-requests",
                       json={"artifact_ids": arts, "requested_by": "dev-agent"})
    assert resp.status_code == 200
    aid = resp.json()["approval_id"]
    assert resp.json()["decision"] == "PENDING"
    # self-approve denied
    resp = client.post(f"/api/approval-requests/{aid}/approve", json={"decided_by": "dev-agent"})
    assert resp.status_code == 403
    # human approve
    resp = client.post(f"/api/approval-requests/{aid}/approve", json={"decided_by": "human", "reason": "ok"})
    assert resp.status_code == 200
    assert resp.json()["decision"] == "APPROVED"
    # list
    resp = client.get("/api/approval-requests")
    assert resp.status_code == 200
    assert any(x["approval_id"] == aid for x in resp.json()["items"])


# --- Real Approve E2E ---

def test_real_approve_e2e(tmp_path):
    """approval → release allowed → (Apply 由 Lifecycle 负责)。"""
    rid, arts = _completed_run(tmp_path)
    from factory_console.production_evaluation import evaluate as _ev
    _ev(str(tmp_path), rid)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="release-engineer")
    assert a["decision"] == "PENDING"
    approve(str(tmp_path), a["approval_id"], decided_by="human", reason="release approved")
    r = release(str(tmp_path), rid, approval_id=a["approval_id"])
    assert r["allowed"] is True
    # audit 事件存在
    from factory_console.audit.audit_store import AuditStore
    store = AuditStore(workspace=None,
                       file=str(Path(tmp_path) / "audit" / "audit_events.json"))
    events = store.events()
    types = {getattr(e, "event_type", "") for e in events}
    assert "APPROVAL_REQUESTED" in types or "APPROVAL_DECIDED" in types


# --- Real Reject E2E ---

def test_real_reject_e2e(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="release-engineer")
    reject(str(tmp_path), a["approval_id"], decided_by="human", reason="not ready")
    r = release(str(tmp_path), rid, approval_id=a["approval_id"])
    assert r["allowed"] is False
    assert get_approval(str(tmp_path), a["approval_id"])["decision"] == "REJECTED"
