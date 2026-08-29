"""S20: Release Verification Pipeline + Approval Expiration。

覆盖:
- Release Verification (apply 后真实 pytest/syntax, VERIFYING→RELEASED/FAILED)
- Release 不能绕过 Verification (apply 成功 ≠ RELEASED)
- Verification evidence (checks: command/exit_code/stdout/stderr)
- Rollback Verification
- Approval Expiration (expires_at + fake clock deterministic)
- Expired approval → BLOCKED (approval_expired reason)
- New approval after expiration works
- CLI / API
- Real E2E
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run, get_production_run,
)
from factory_console.production_evaluation import evaluate  # noqa: E402
from factory_console.governance_service import (  # noqa: E402
    request_approval, approve, check_governance, set_clock,
)
from factory_console.release_service import (  # noqa: E402
    create as rel_create, execute as rel_execute, get_release,
)
from factory_console.rollback_service import (  # noqa: E402
    create as rb_create, execute as rb_execute, get_rollback,
)


def _patch(fname: str, body: str = "def x():\n    return 1\n") -> str:
    lines = "".join(f"+{ln}\n" for ln in body.rstrip("\n").split("\n"))
    return f"diff --git a/{fname} b/{fname}\n--- /dev/null\n+++ b/{fname}\n@@ -0,0 +1,{len(body.rstrip(chr(10)).split(chr(10)))} @@\n{lines}"


def _run_release(tmp_path, fname: str, body: str = "def x():\n    return 1\n") -> tuple[str, list[str], str]:
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
    patch = _patch(fname, body)

    def factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"}, "patch_text": patch,
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    run2 = get_production_run(str(tmp_path), run["run_id"])
    evaluate(str(tmp_path), run["run_id"])
    arts = list(run2.get("artifacts", []))
    a = request_approval(str(tmp_path), production_run_id=run["run_id"],
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    rel = rel_create(str(tmp_path), run["run_id"])
    r = rel_execute(str(tmp_path), rel["release_id"])
    return run["run_id"], arts, r["release"]["release_id"]


# --- Release Verification Pipeline ---

def test_release_verified_after_apply(tmp_path):
    """Release apply 后必须经过 VERIFYING → RELEASED (非直接)。"""
    rid, arts, rel_id = _run_release(tmp_path, "a.py")
    rel = get_release(str(tmp_path), rel_id)
    assert rel["state"] == "RELEASED"
    states = [h["to"] for h in rel["history"]]
    assert "VERIFYING" in states
    assert states[-1] == "RELEASED"
    # verification checks 持久化
    assert rel.get("verification_checks"), "必须有 verification checks"


def test_release_verification_evidence(tmp_path):
    rid, arts, rel_id = _run_release(tmp_path, "a.py")
    rel = get_release(str(tmp_path), rel_id)
    for c in rel["verification_checks"]:
        assert "type" in c and "status" in c and "exit_code" in c
        assert c["status"] in ("PASS", "FAIL")


def test_release_verification_failure_not_released(tmp_path):
    """Release apply 成功但 workspace 语法坏 → FAILED (不 RELEASED)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
    # 坏的 Python (语法错误) 但 patch 能 apply
    patch = _patch("bad.py", "def broken(:\n    return\n")

    def factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"}, "patch_text": patch,
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    run2 = get_production_run(str(tmp_path), run["run_id"])
    evaluate(str(tmp_path), run["run_id"])
    arts = list(run2.get("artifacts", []))
    a = request_approval(str(tmp_path), production_run_id=run["run_id"],
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    rel = rel_create(str(tmp_path), run["run_id"])
    r = rel_execute(str(tmp_path), rel["release_id"])
    assert r["release"]["state"] == "FAILED", "语法坏 → release 必须 FAILED"
    assert r["release"]["failure_reason"]
    assert "verification" in r["release"]["failure_reason"].lower()


# --- Rollback Verification ---

def test_rollback_verified(tmp_path):
    """Rollback 后必须经过 VERIFYING → ROLLED_BACK。"""
    ra, arts_a, rel_a = _run_release(tmp_path, "a.py")
    rb_, arts_b, rel_b = _run_release(tmp_path, "b.py")
    rb = rb_create(str(tmp_path), rel_a)
    r = rb_execute(str(tmp_path), rb["rollback_id"])
    assert r["rollback"]["state"] == "ROLLED_BACK", r
    states = [h["to"] for h in r["rollback"]["history"]]
    assert "VERIFYING" in states
    assert get_rollback(str(tmp_path), rb["rollback_id"]).get("verification_checks")


# --- Approval Expiration (fake clock) ---

def test_approval_expiration_blocked(tmp_path):
    """expired approval → release BLOCKED (approval_expired)。"""
    t0 = time.time()
    set_clock(lambda: t0)
    try:
        rid, arts, rel_id = _run_release(tmp_path, "a.py")
        # 时间前进 25h → approval 过期
        set_clock(lambda: t0 + 25 * 3600)
        g = check_governance(str(tmp_path), rid, action="release")
        assert g["allowed"] is False
        assert "approval_expired" in g["missing"]
        assert g.get("approval_expired") is True
    finally:
        set_clock(lambda: time.time())


def test_new_approval_after_expiry(tmp_path):
    """过期后新 approval → release 正常。"""
    t0 = time.time()
    set_clock(lambda: t0)
    try:
        rid, arts, rel_id = _run_release(tmp_path, "a.py")
        # 过期 → 新 approval
        set_clock(lambda: t0 + 25 * 3600)
        a2 = request_approval(str(tmp_path), production_run_id=rid,
                              artifact_ids=arts, requested_by="dev-agent")
        approve(str(tmp_path), a2["approval_id"], decided_by="human")
        g = check_governance(str(tmp_path), rid, action="release")
        assert g["allowed"] is True, g
    finally:
        set_clock(lambda: time.time())


def test_expired_approval_not_reusable_other_run(tmp_path):
    """过期 approval 不能用于其他 run。"""
    t0 = time.time()
    set_clock(lambda: t0)
    try:
        rid1, arts1, rel1 = _run_release(tmp_path, "a.py")
        rid2, arts2, rel2 = _run_release(tmp_path, "b.py")
        set_clock(lambda: t0 + 25 * 3600)
        # run1 的 approval 过期 → run1 BLOCKED
        g1 = check_governance(str(tmp_path), rid1, action="release")
        assert g1["allowed"] is False
        assert "approval_expired" in g1["missing"]
    finally:
        set_clock(lambda: time.time())


# --- CLI ---

def test_cli_release_verify(tmp_path):
    rid, arts, rel_id = _run_release(tmp_path, "a.py")
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["release", "verify", rel_id, "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_verification(tmp_path):
    rid, arts, rel_id = _run_release(tmp_path, "a.py")
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get(f"/api/releases/{rel_id}/verification")
    assert resp.status_code == 200
    assert resp.json()["state"] == "RELEASED"
    assert "verification_checks" in resp.json()


# --- Real E2E: release verify → pytest PASS ---

def test_release_pytest_verification_e2e(tmp_path):
    """Release 后 workspace 真实可跑 pytest (真实 subprocess)。"""
    import subprocess
    rid, arts, rel_id = _run_release(tmp_path, "calc.py",
                                     body="def add(a, b):\n    return a + b\n")
    rel = get_release(str(tmp_path), rel_id)
    assert rel["state"] == "RELEASED"
    # 写 pytest 到 workspace 再验证 (真实 subprocess)
    ws = Path(tmp_path) / "workspace"
    (ws / "test_calc.py").write_text(
        "import calc\n\ndef test_add():\n    assert calc.add(2, 3) == 5\n", encoding="utf-8")
    from factory_console.verification import verify_pytest
    r = verify_pytest(ws)
    assert r["status"] == "PASS"
