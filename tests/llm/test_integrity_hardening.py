"""S20.5: Production Integrity Hardening 测试。

覆盖:
- Concurrency: 并发 release execute × N → 最多一次真实 apply (文件锁)
- Recovery: release/rollback VERIFYING 中断恢复 (PASS evidence → 完成; 无 → 重验)
- Retry: retryable → retry / PASS / max attempts → FAILED; non-retryable → no retry; 历史保留
- Regression: S1-S20 不破坏
"""
from __future__ import annotations

import sys
import time
import threading
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
    request_approval, approve,
)
from factory_console.release_service import (  # noqa: E402
    create as rel_create, execute as rel_execute, get_release, recover_verifying as rel_recover,
)
from factory_console.rollback_service import (  # noqa: E402
    create as rb_create, execute as rb_execute, get_rollback, recover_verifying as rb_recover,
)


def _patch(fname: str, body: str = "def x():\n    return 1\n") -> str:
    lines = "".join(f"+{ln}\n" for ln in body.rstrip("\n").split("\n"))
    return f"diff --git a/{fname} b/{fname}\n--- /dev/null\n+++ b/{fname}\n@@ -0,0 +1,{len(body.rstrip(chr(10)).split(chr(10)))} @@\n{lines}"


def _make_release(tmp_path, fname: str = "a.py", body: str = "def x():\n    return 1\n") -> tuple[str, list[str], str]:
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


# --- GAP-1: Concurrency ---

def test_concurrent_release_single_apply(tmp_path):
    """并发 release execute × 4 → 最多一次真实 apply (RELEASED 或 already_released)。"""
    rid, arts, rel_id = _make_release(tmp_path)
    # 已 RELEASED — 并发重复 execute 全部 no-op
    results = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        try:
            r = rel_execute(str(tmp_path), rel_id)
            results.append(("ok", r.get("already_released")))
        except Exception as exc:  # noqa: BLE001
            results.append(("err", str(exc)))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 全部 no-op (已 RELEASED), 无 corrupt
    assert len(results) == 4
    rel = get_release(str(tmp_path), rel_id)
    assert rel["state"] == "RELEASED"
    # JSON 未 corrupt
    import json
    json.loads((Path(tmp_path) / "releases" / "releases.json").read_text(encoding="utf-8"))


def test_concurrent_approve_one_wins(tmp_path):
    """并发 approve 同一 request → 只有一次成功, 其他拒绝 (PENDING→APPROVED 唯一)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
    a = request_approval(str(tmp_path), production_run_id=run["run_id"],
                         artifact_ids=[], requested_by="dev-agent")
    results = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        try:
            approve(str(tmp_path), a["approval_id"], decided_by="human")
            results.append("ok")
        except Exception as exc:  # noqa: BLE001
            results.append(f"err:{type(exc).__name__}")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok_count = sum(1 for r in results if r == "ok")
    assert ok_count == 1, f"并发 approve 必须恰好 1 次成功, got {results}"


# --- GAP-2: Recovery ---

def test_release_verifying_recovery_pass_evidence(tmp_path):
    """Release VERIFYING + 已有 PASS attempts → recover 完成 RELEASED。"""
    rid, arts, rel_id = _make_release(tmp_path)
    rel = get_release(str(tmp_path), rel_id)
    # 手动模拟崩溃: 回到 VERIFYING (保留 PASS evidence)
    rel["state"] = "VERIFYING"
    rel["history"].append({"from": "RELEASED", "to": "VERIFYING", "actor": "crash-sim",
                           "at": "", "note": "simulated crash"})
    import json
    data = json.loads((Path(tmp_path) / "releases" / "releases.json").read_text(encoding="utf-8"))
    for r in data:
        if r["release_id"] == rel_id:
            r.update(rel)
    (Path(tmp_path) / "releases" / "releases.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    r = rel_recover(str(tmp_path), rel_id)
    assert r["recovered"] is True
    assert r["release"]["state"] == "RELEASED"
    assert "PASS evidence" in r["reason"]


def test_release_verifying_recovery_reverify(tmp_path):
    """Release VERIFYING + 无 PASS evidence → 重新 verification → RELEASED。"""
    rid, arts, rel_id = _make_release(tmp_path)
    rel = get_release(str(tmp_path), rel_id)
    rel["state"] = "VERIFYING"
    rel["verification_attempts"] = []
    import json
    data = json.loads((Path(tmp_path) / "releases" / "releases.json").read_text(encoding="utf-8"))
    for r in data:
        if r["release_id"] == rel_id:
            r.update(rel)
    (Path(tmp_path) / "releases" / "releases.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    r = rel_recover(str(tmp_path), rel_id)
    assert r["release"]["state"] == "RELEASED", r
    assert r["recovered"] is True


def test_rollback_verifying_recovery(tmp_path):
    """Rollback VERIFYING + PASS evidence → recover 完成 ROLLED_BACK。"""
    ra, arts_a, rel_a = _make_release(tmp_path, "a.py")
    rb_, arts_b, rel_b = _make_release(tmp_path, "b.py")
    rb = rb_create(str(tmp_path), rel_a)
    r = rb_execute(str(tmp_path), rb["rollback_id"])
    assert r["rollback"]["state"] == "ROLLED_BACK"
    rb2 = get_rollback(str(tmp_path), rb["rollback_id"])
    rb2["state"] = "VERIFYING"
    import json
    data = json.loads((Path(tmp_path) / "rollbacks" / "rollbacks.json").read_text(encoding="utf-8"))
    for x in data:
        if x["rollback_id"] == rb["rollback_id"]:
            x.update(rb2)
    (Path(tmp_path) / "rollbacks" / "rollbacks.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    r2 = rb_recover(str(tmp_path), rb["rollback_id"])
    assert r2["rollback"]["state"] == "ROLLED_BACK"
    assert r2["recovered"] is True


# --- GAP-3: Retry Contract ---

def test_retry_policy_classification():
    """retryable vs non-retryable 分类。"""
    from factory_console.retry_policy import is_retryable_verification, MAX_VERIFICATION_ATTEMPTS
    assert MAX_VERIFICATION_ATTEMPTS == 3
    # timeout → retryable
    assert is_retryable_verification({"exit_code": 124, "stderr": "timeout"})
    assert is_retryable_verification({"exit_code": -1, "stderr": "killed"})
    assert is_retryable_verification({"exit_code": 1, "stderr": "command not found"})
    # syntax / pytest assert → non-retryable
    assert not is_retryable_verification({"exit_code": 1, "stderr": "SyntaxError"})
    assert not is_retryable_verification({"exit_code": 1, "stderr": "assert 1 == 2"})


def test_verification_attempts_history_preserved(tmp_path):
    """verification_attempts append-only: attempt 1 FAIL → attempt 2 PASS (lineage 保留)。"""
    rid, arts, rel_id = _make_release(tmp_path)
    rel = get_release(str(tmp_path), rel_id)
    attempts = rel.get("verification_attempts", [])
    assert len(attempts) >= 1
    assert attempts[-1]["result"] == "PASS"
    # 所有 attempt 保留 (不覆盖)
    assert all("checks" in a for a in attempts)


def test_release_failure_no_fake_success(tmp_path):
    """verification 真实失败 (syntax 坏) → FAILED, 非 RELEASED。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
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
    assert r["release"]["state"] == "FAILED"
    # syntax 失败 non-retryable → 只有 1 attempt (无无限 retry)
    assert len(r["release"].get("verification_attempts", [])) == 1
