"""S28: Production Quality Recovery & Verification Closure。

覆盖:
- Case A: verification FAIL → repair → re-verification PASS → RECOVERED
- Case B: 连续 FAIL → bounded retry → EXHAUSTED
- Case C: 非 repair 类 (AGENT/GOV) → BLOCKED (不自动)
- Idempotency (已终态 → ALREADY_CLOSED)
- 历史 append-only (attempts 保留失败)
- 新 verification_id (不复用旧)
- Lineage (run → classification → attempts → outcome)
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run,
)
from factory_console.recovery_service import (  # noqa: E402
    recover_production_run, recovery_status, recovery_attempts,
    recovery_lineage, recovery_policy, MAX_ATTEMPTS,
)


def _wf(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    (Path(tmp_path) / "workspace").mkdir(exist_ok=True)


GOOD = "def a():\n    return 1\n"
BAD = "def broken(:\n    pass\n"


def _fail_then_ok_factory(ws, fails: int = 1):
    """首次 fails 次写坏代码, 之后写好 (模拟 LLM 修复)。"""
    state = {"n": 0}

    def factory(node_id):
        def fn(input_data):
            state["n"] += 1
            if state["n"] <= fails:
                (ws / "a.py").write_text(BAD)
                return {"ok": False, "error": "内置 pytest 失败: SyntaxError",
                        "verification": {"result": "FAIL"}}
            (ws / "a.py").write_text(GOOD)
            return {"ok": True, "output": {"code": "ok"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n" + GOOD),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    return factory


def _always_bad_factory(ws):
    def factory(node_id):
        def fn(input_data):
            (ws / "a.py").write_text(BAD)
            return {"ok": False, "error": "内置 pytest 失败: SyntaxError",
                    "verification": {"result": "FAIL"}}
        return fn
    return factory


def _repair_ok(ws):
    def repair(failed_artifact, verification, ctx):
        (ws / "a.py").write_text(GOOD)
        return {"ok": True, "output": {"code": "ok"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n" + GOOD),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return repair


def _repair_bad(ws):
    def repair(failed_artifact, verification, ctx):
        (ws / "a.py").write_text("def still_broken(:\n    pass\n")
        return {"ok": False, "error": "内置 pytest 失败: 未修复",
                "verification": {"result": "FAIL"}}
    return repair


def _make_failed_run(tmp_path, factory) -> str:
    r = create_production_run(str(tmp_path), "wf-1")
    execute_production_run(str(tmp_path), r["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    return r["run_id"]


# --- Case A: FAIL → repair → PASS → RECOVERED ---

def test_case_a_recovered(tmp_path):
    _wf(tmp_path)
    ws = Path(tmp_path) / "workspace"
    run_id = _make_failed_run(tmp_path, _fail_then_ok_factory(ws, fails=1))
    res = recover_production_run(str(tmp_path), run_id,
                                 executor_factory=_fail_then_ok_factory(ws, fails=1),
                                 repair_fn=_repair_ok(ws))
    assert res["status"] == "RECOVERED"
    assert res["verification"]["result"] == "PASS"
    assert res["verification"]["verification_id"].startswith("ver-")  # 新 verification_id
    assert (ws / "a.py").read_text() == GOOD  # 真实修复


# --- Case B: 连续 FAIL → EXHAUSTED ---

def test_case_b_exhausted(tmp_path):
    _wf(tmp_path)
    ws = Path(tmp_path) / "workspace"
    run_id = _make_failed_run(tmp_path, _always_bad_factory(ws))
    res = recover_production_run(str(tmp_path), run_id,
                                 executor_factory=_always_bad_factory(ws),
                                 repair_fn=_repair_bad(ws))
    assert res["status"] == "EXHAUSTED"
    assert res["attempt_number"] == MAX_ATTEMPTS
    # 历史 append-only: attempts 含全部失败
    attempts = recovery_attempts(str(tmp_path), run_id)
    assert len(attempts) >= MAX_ATTEMPTS
    assert any(a["status"] == "VERIFICATION_PENDING" for a in attempts)


# --- Case C: 非 repair 类 → BLOCKED ---

def test_case_c_blocked(tmp_path):
    _wf(tmp_path)
    ws = Path(tmp_path) / "workspace"

    def agent_bad(node_id):
        def fn(input_data):
            return {"ok": False, "error": "未知角色: developer"}
        return fn
    run_id = _make_failed_run(tmp_path, agent_bad)
    res = recover_production_run(str(tmp_path), run_id,
                                 executor_factory=agent_bad, repair_fn=_repair_ok(ws))
    assert res["status"] == "BLOCKED"
    assert "不可自动" in res["note"]


# --- Idempotency ---

def test_idempotent(tmp_path):
    _wf(tmp_path)
    ws = Path(tmp_path) / "workspace"
    run_id = _make_failed_run(tmp_path, _fail_then_ok_factory(ws, fails=1))
    recover_production_run(str(tmp_path), run_id,
                           executor_factory=_fail_then_ok_factory(ws, fails=1),
                           repair_fn=_repair_ok(ws))
    res2 = recover_production_run(str(tmp_path), run_id,
                                  executor_factory=_fail_then_ok_factory(ws, fails=1),
                                  repair_fn=_repair_ok(ws))
    assert res2["status"] == "ALREADY_CLOSED"


# --- Recovery Policy ---

def test_policy(tmp_path):
    assert recovery_policy(str(tmp_path), "VERIFICATION_FAILURE")["allowed"] is True
    assert recovery_policy(str(tmp_path), "AGENT_FAILURE")["allowed"] is False
    assert recovery_policy(str(tmp_path), "UNKNOWN")["allowed"] is False


# --- Lineage ---

def test_lineage(tmp_path):
    _wf(tmp_path)
    ws = Path(tmp_path) / "workspace"
    run_id = _make_failed_run(tmp_path, _fail_then_ok_factory(ws, fails=1))
    recover_production_run(str(tmp_path), run_id,
                           executor_factory=_fail_then_ok_factory(ws, fails=1),
                           repair_fn=_repair_ok(ws))
    lg = recovery_lineage(str(tmp_path), run_id)
    assert lg["failure_classification"] == "VERIFICATION_FAILURE"
    assert lg["outcome"] == "RECOVERED"
    assert lg["attempts"][-1]["verification_result"] == "PASS"


# --- 新 verification_id 不复用 ---

def test_new_verification_id(tmp_path):
    _wf(tmp_path)
    ws = Path(tmp_path) / "workspace"
    run_id = _make_failed_run(tmp_path, _fail_then_ok_factory(ws, fails=1))
    res = recover_production_run(str(tmp_path), run_id,
                                 executor_factory=_fail_then_ok_factory(ws, fails=1),
                                 repair_fn=_repair_ok(ws))
    # 每个 attempt 有独立 verification_id
    attempts = recovery_attempts(str(tmp_path), run_id)
    vids = [a.get("verification", {}).get("verification_id") for a in attempts if a.get("verification")]
    assert len(set(vids)) == len(vids)  # 全部唯一


# --- CLI ---

def test_cli_recovery(tmp_path):
    _wf(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["recovery", "status", "prun-x", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["recovery", "attempts", "prun-x", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["recovery", "evidence", "rec-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_recovery(tmp_path):
    _wf(tmp_path)
    ws = Path(tmp_path) / "workspace"
    run_id = _make_failed_run(tmp_path, _fail_then_ok_factory(ws, fails=1))
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get(f"/api/production-runs/{run_id}/recovery")
    assert resp.status_code == 200
    resp = client.post(f"/api/recovery/{run_id}/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("RECOVERED", "EXHAUSTED", "BLOCKED")
    st = client.get(f"/api/production-runs/{run_id}/recovery").json()
    assert st["status"] in ("RECOVERED", "EXHAUSTED", "BLOCKED")
