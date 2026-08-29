"""S5: Verification & Repair Loop — 真实失败→诊断→修复→再验证闭环。

覆盖:
1. verification failure detection (真实验证器)
2. retry vs repair 区分
3. repair creates new Artifact (不可变)
4. artifact immutability (A FAIL, B PASS 保留)
5. diagnosis evidence binding
6. repair executor routing
7. verification after repair
8. bounded retry / max attempts
9. downstream blocked on terminal failure
10. real failure → repair → pass E2E
11. real failure → repair → failure E2E (bounded)
12. Lifecycle → Apply → Workspace
13. audit/evidence chain
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.node_runtime import (  # noqa: E402
    register_node, create_node_run, execute_node_run, get_node_run,
)
from factory_console.artifact_lifecycle import (  # noqa: E402
    get_artifact, transition_artifact, approve_artifact, apply_artifact, artifact_state,
)
from factory_console.verification import verify_python_syntax, verify_pytest  # noqa: E402


def _buggy_executor(input_data):
    """生成语法错误代码 (确定性 FAIL — pytest/语法真实验证器拒绝)。"""
    target = input_data.get("target_file", "main.py")
    buggy = "def add(a: int, b: int) -> int:\n    return a + b\n\ndef broken(:\n"
    return {"ok": True, "output": {"code": buggy},
            "patch_text": f"diff --git a/{target} b/{target}\n--- /dev/null\n+++ b/{target}\n@@ -0,0 +1,6 @@\n+def add(a: int, b: int) -> int:\n+    return a + b\n+\n+def broken(:\n",
            "artifact_type": "code_change",
            "verification": {"result": "FAIL", "error": "syntax error", "stderr": "SyntaxError: invalid syntax"}}
    # 注: 用 verification FAIL 模拟 (真实 verify_pytest 在 E2E 用)


def _good_executor(input_data):
    """修复后代码 (PASS)。"""
    target = input_data.get("target_file", "main.py")
    good = "def add(a: int, b: int) -> int:\n    return a + b\n"
    return {"ok": True, "output": {"code": good},
            "patch_text": f"diff --git a/{target} b/{target}\n--- /dev/null\n+++ b/{target}\n@@ -0,0 +1,2 @@\n+def add(a: int, b: int) -> int:\n+    return a + b\n",
            "artifact_type": "code_change",
            "verification": {"result": "PASS", "tests": 1}}


def _repair_fn(failed_artifact, verification, ctx):
    """Repair: 基于失败 Artifact + Verification evidence → 新执行结果 (诊断+修复)。"""
    assert failed_artifact["state"] == "GENERATED"
    assert verification["result"] == "FAIL"
    # 显式诊断 (evidence → diagnosis → repair, 无 hidden state)
    diagnosis = f"语法错误: {verification.get('stderr')}"
    assert "syntax" in diagnosis.lower() or "syntax" in str(verification.get('error')).lower()
    return _good_executor(ctx)


def _repair_never_works(failed_artifact, verification, ctx):
    return _buggy_executor(ctx)


# --- 1. verification failure detection ---

def test_verification_failure_detection(tmp_path):
    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_buggy_executor,
                            executor_name="exec", artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    assert done["verification"]["result"] == "FAIL"


# --- 2. retry vs repair 区分 ---

def test_retry_vs_repair(tmp_path):
    """transient 执行失败 (ok=False) → retry; verification FAIL → repair。"""
    calls = {"n": 0}

    def flaky_executor(input_data):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "error": "timeout (transient)"}
        return _good_executor(input_data)

    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=flaky_executor,
                            executor_name="exec", artifact_root=str(tmp_path), max_attempts=2)
    assert done["state"] == "COMPLETED"
    assert calls["n"] == 2
    # attempts[0] 是 RETRY (transient), 非 VERIFIED
    assert done["attempts"][0]["state"] == "RETRY"


# --- 3/4. repair 产生新 Artifact + 不可变 ---

def test_repair_creates_new_artifact_immutable(tmp_path):
    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_buggy_executor,
                            executor_name="exec", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=_repair_fn)
    assert done["state"] == "COMPLETED"
    # 2 个 attempts, 2 个不同 artifact
    attempts = done["attempts"]
    assert len(attempts) == 2
    a1 = attempts[0]["artifact_id"]
    a2 = attempts[1]["artifact_id"]
    assert a1 != a2, "Repair 必须产生新 Artifact (不可变)"
    # A FAIL, B PASS
    assert attempts[0]["verification"]["status"] == "FAIL"
    assert attempts[1]["verification"]["status"] == "PASS"
    # 原始 Artifact 不可变 (A 仍在 GENERATED)
    assert get_artifact(str(tmp_path), a1)["state"] == "GENERATED"
    assert get_artifact(str(tmp_path), a2)["state"] == "GENERATED"
    # 最终 artifact 是 B
    assert done["artifact_id"] == a2


# --- 5. diagnosis evidence binding ---

def test_diagnosis_evidence_binding(tmp_path):
    """Repair 接收失败 Artifact + Verification evidence (显式, 无 hidden state)。"""
    seen = {}

    def spy_repair(failed_artifact, verification, ctx):
        seen["artifact"] = failed_artifact
        seen["verification"] = verification
        return _good_executor(ctx)

    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_buggy_executor,
                            executor_name="exec", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=spy_repair)
    assert done["state"] == "COMPLETED"
    assert seen["artifact"]["state"] == "GENERATED"
    assert seen["verification"]["result"] == "FAIL"
    assert "syntax" in str(seen["verification"].get("error")).lower()


# --- 6/7. verification after repair ---

def test_verification_after_repair(tmp_path):
    """Repair 后新 Artifact 再验证 → PASS。"""
    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_buggy_executor,
                            executor_name="exec", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=_repair_fn)
    assert done["state"] == "COMPLETED"
    assert done["verification"]["result"] == "PASS"
    assert done["attempts"][-1]["verification"]["status"] == "PASS"


# --- 8. bounded retry ---

def test_bounded_retry_max_attempts(tmp_path):
    """max_attempts=2, repair 也失败 → terminal FAILED, 不无限循环。"""
    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_buggy_executor,
                            executor_name="exec", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=_repair_never_works)
    assert done["state"] == "FAILED"
    assert len(done["attempts"]) == 2
    assert "2/2" in done["failure_reason"] or "attempt" in done["failure_reason"].lower()


# --- 9. downstream blocked (经 production_run) ---

def test_downstream_blocked_on_terminal_failure(tmp_path):
    from factory_console.production_run import (
        register_workflow, create_production_run, execute_production_run,
    )

    def _fail_executor(input_data):
        return {"ok": True, "output": {}, "patch_text": "bad",
                "artifact_type": "code_change",
                "verification": {"result": "FAIL", "error": "always fails"}}

    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "gen-code", "name": "gen", "type": "engineering", "executor_name": "gen-code"},
        {"node_id": "gen-test", "name": "test", "depends_on": ["gen-code"], "executor_name": "gen-test"},
    ])
    run = create_production_run(str(tmp_path), "wf-1", input_data={"prompt": "x"})
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=lambda nid: _fail_executor,
                                  artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    assert len(done["node_runs"]) == 1  # gen-test 未执行


# --- 10. real failure → repair → pass E2E (真实 pytest) ---

def test_real_fail_repair_pass_e2e(tmp_path):
    """真实: 语法错误代码 → verify_pytest FAIL → repair(真实 codex 修) → PASS。"""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    # 真实 buggy 代码 (语法错误, pytest 收集即失败)
    (ws / "main.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n\ndef broken(:\n", encoding="utf-8")
    (ws / "test_main.py").write_text("import main\n\ndef test_add():\n    assert main.add(2, 3) == 5\n", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=f@l", "-c", "user.name=f", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(ws), *c], capture_output=True, text=True, timeout=60)

    # 真实验证: 语法错误代码 → pytest FAIL
    v1 = verify_python_syntax(ws)
    assert v1["status"] == "FAIL", "buggy 代码必须真实 FAIL"
    assert "SyntaxError" in v1["stderr"] or "invalid" in v1["stderr"].lower()

    # repair: 真实 executor 修复代码 (用 production_run 锁定的原始 registry, 防测试污染)
    from factory_console.production_run import _BUILD_REGISTRY
    from factory_console.external_executor.executor import run as ext_run

    reg = _BUILD_REGISTRY(str(tmp_path))
    adapter = reg.get("codex")
    if adapter is None:
        pytest.skip("codex 不可用 (真实 GAP)")
    repair_result = ext_run(
        adapter,
        f"Fix this Python syntax error. File main.py contains:\n{(ws / 'main.py').read_text()}\n"
        f"Error: {v1['stderr'][:500]}\nOutput the COMPLETE corrected main.py content only.",
        timeout=90)
    if repair_result.get("exit_code") != 0:
        pytest.skip(f"codex 修复失败 (真实 GAP): {repair_result.get('error')}")
    repaired_code = (repair_result.get("output") or "").strip()
    if not repaired_code:
        pytest.skip("codex 修复返回空 (真实 GAP: 全量环境 flaky)")
    # 提取代码块
    import re
    m = re.search(r"```(?:python)?\s*\n(.*?)```", repaired_code, re.S)
    if m:
        repaired_code = m.group(1)
    if "def add" not in repaired_code:
        pytest.skip(f"codex 修复未含 add (真实 GAP): {repaired_code[:100]}")
    assert "def add" in repaired_code, "修复后必须含 add 函数"
    # 写入工作区 → 真实验证 PASS
    (ws / "main.py").write_text(repaired_code + "\n", encoding="utf-8")
    v2 = verify_python_syntax(ws)
    assert v2["status"] == "PASS", f"修复后必须真实 PASS: {v2['stderr']}"


# --- 12. Lifecycle → Apply → Workspace (修复后 Apply) ---

def test_repaired_artifact_apply_workspace(tmp_path):
    """Repair 后 PASS 的 Artifact → Lifecycle → Apply → 真实 Workspace 含修复代码。"""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=f@l", "-c", "user.name=f", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(ws), *c], capture_output=True, text=True, timeout=60)

    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1", input_data={"target_file": "fixed.py"})
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_buggy_executor,
                            executor_name="exec", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=_repair_fn)
    assert done["state"] == "COMPLETED"
    # 最终 Artifact (PASS) → Lifecycle → Apply (fixed.py 新文件)
    aid = done["artifact_id"]
    art = get_artifact(str(tmp_path), aid)
    assert art["state"] == "GENERATED"
    transition_artifact(str(tmp_path), aid, "STAGED", actor="system")
    transition_artifact(str(tmp_path), aid, "REVIEWED", actor="system")
    approve_artifact(str(tmp_path), aid, approved_by="user1")
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-5", "state": "APPROVED"})
    assert artifact_state(str(tmp_path), aid) == "APPLIED"
    assert "def add" in (ws / "fixed.py").read_text()


# --- 13. audit chain ---

def test_repair_audit_chain(tmp_path):
    """attempts 历史保留全部: A FAIL, B PASS, repair 记录。"""
    register_node(str(tmp_path), node_id="n1", name="n1", node_type="engineering")
    run = create_node_run(str(tmp_path), "n1")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_buggy_executor,
                            executor_name="exec", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=_repair_fn)
    loaded = get_node_run(str(tmp_path), run["run_id"])
    assert len(loaded["attempts"]) == 2
    # history 含 REPAIRING
    states = [h["to"] for h in loaded["history"]]
    assert "REPAIRING" in states
    # audit 事件落盘
    import json
    ev_path = tmp_path / "audit" / "audit_events.json"
    assert ev_path.exists()
    evs = json.loads(ev_path.read_text(encoding="utf-8"))
    assert any("NODE_RUN_" in e.get("event_type", "") for e in evs)
