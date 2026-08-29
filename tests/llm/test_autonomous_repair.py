"""S12: Autonomous Failure Recovery & Repair Loop — 真实 pytest FAIL → 自动修复 → PASS。

覆盖:
1. pytest failure produces Failure Evidence
2. failure automatically triggers Repair (无人工)
3. Repair consumes failure evidence
4. Repair creates new Artifact (A != B)
5. Artifact lineage preserved
6. pytest re-executes after Repair
7. FAIL → PASS state transition
8. max repair attempts (bounded)
9. final Apply → Workspace
10. full lineage
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

from factory_console.professional_workflow import (  # noqa: E402
    verify_code_with_pytest, BUILTIN_CALC_TESTS, ensure_professional_agents,
    run_professional_workflow, build_developer_repair_fn,
)
from factory_console.node_runtime import (  # noqa: E402
    register_node, create_node_run, execute_node_run, get_node_run,
)
from factory_console.artifact_lifecycle import get_artifact  # noqa: E402


# --- 1. pytest failure produces evidence ---

def test_pytest_failure_evidence(tmp_path):
    """真实 pytest FAIL → 完整 failure evidence (exit_code/stdout/stderr)。"""
    bad_code = "def add(a, b):\n    return a - b\n"  # 故意错
    r = verify_code_with_pytest(bad_code, BUILTIN_CALC_TESTS)
    assert r["status"] == "FAIL"
    assert r["exit_code"] != 0
    assert "command" in r and "stdout" in r and "stderr" in r
    assert "verification_id" in r


# --- 2/3/4/5/6/7. 自动修复闭环 (确定性 repair) ---

def test_autonomous_repair_loop(tmp_path):
    """pytest FAIL → 自动 repair (无人工) → 新 Artifact → 再 pytest → PASS。"""
    register_node(str(tmp_path), node_id="dev", name="dev", node_type="engineering")

    bad_code = ("def add(a, b):\n    return a - b\n\ndef subtract(a, b):\n    return a + b\n\n"
                "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    return a / b\n")
    good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                 "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                 "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")
    calls = {"exec": 0, "repair": 0}

    def exec_fn(input_data):
        calls["exec"] += 1
        code = input_data.get("_code", bad_code)
        ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
        return {"ok": True, "output": {"content": code}, "patch_text": "",
                "artifact_type": "code_change", "verification": ver, "content": code}

    def repair_fn(failed_artifact, verification, ctx):
        calls["repair"] += 1
        # repair 消费 failure evidence
        assert verification["status"] == "FAIL"
        assert "stdout" in verification or "stderr" in verification
        # 原 artifact 是 failed 的
        assert failed_artifact["state"] == "GENERATED"
        return exec_fn({**dict(ctx), "_code": good_code})

    run = create_node_run(str(tmp_path), "dev")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=exec_fn,
                            executor_name="dev", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=repair_fn)
    assert done["state"] == "COMPLETED"
    assert calls["repair"] == 1, "必须自动触发 repair (无人工)"
    a1 = done["attempts"][0]["artifact_id"]
    a2 = done["attempts"][1]["artifact_id"]
    assert a1 != a2, "Repair 必须产生新 Artifact"
    # lineage: attempts 记录 FAIL → PASS
    assert done["attempts"][0]["verification"]["status"] == "FAIL"
    assert done["attempts"][1]["verification"]["status"] == "PASS"
    # 原 Artifact 保留 (不可变)
    assert get_artifact(str(tmp_path), a1)["state"] == "GENERATED"


# --- 8. max repair attempts (bounded) ---

def test_max_repair_bounded(tmp_path):
    """max_attempts=2, repair 也失败 → terminal FAILED (不无限循环)。"""
    register_node(str(tmp_path), node_id="dev", name="dev", node_type="engineering")

    bad_code = "def add(a, b):\n    return a - b\n"
    calls = {"n": 0}

    def exec_fn(input_data):
        calls["n"] += 1
        ver = verify_code_with_pytest(bad_code, BUILTIN_CALC_TESTS)
        return {"ok": True, "output": {"content": bad_code}, "patch_text": "",
                "artifact_type": "code_change", "verification": ver, "content": bad_code}

    def repair_fn(failed_artifact, verification, ctx):
        return exec_fn(ctx)  # repair 也失败 (还是 bad)

    run = create_node_run(str(tmp_path), "dev")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=exec_fn,
                            executor_name="dev", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=repair_fn)
    assert done["state"] == "FAILED"
    assert len(done["attempts"]) == 2
    assert calls["n"] == 2, "不无限循环"


# --- 9. Apply → Workspace (修复后最终代码) ---

def test_repair_apply_workspace(tmp_path):
    """修复后 PASS 的代码 → Apply → 真实 Workspace。"""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=f@l", "-c", "user.name=f", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(ws), *c], capture_output=True, text=True, timeout=60)
    register_node(str(tmp_path), node_id="dev", name="dev", node_type="engineering")

    bad_code = "def add(a, b):\n    return a - b\n"
    good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                 "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                 "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")

    def exec_fn(input_data):
        code = input_data.get("_code", bad_code)
        ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
        return {"ok": True, "output": {"content": code}, "patch_text": "",
                "artifact_type": "code_change", "verification": ver, "content": code}

    def repair_fn(failed_artifact, verification, ctx):
        return exec_fn({**dict(ctx), "_code": good_code})

    run = create_node_run(str(tmp_path), "dev")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=exec_fn,
                            executor_name="dev", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=repair_fn)
    assert done["state"] == "COMPLETED"
    final_artifact = done["artifact_id"]
    art = get_artifact(str(tmp_path), final_artifact)
    content = (art.get("payload") or {}).get("content") or ""
    assert "raise ValueError" in content, "最终代码必须含除零保护 (修复后)"
    (ws / "app.py").write_text(content + "\n", encoding="utf-8")
    # 真实 workspace 可独立跑 pytest
    from factory_console.verification import verify_pytest
    (ws / "test_app.py").write_text(BUILTIN_CALC_TESTS, encoding="utf-8")
    r = verify_pytest(ws)
    assert r["status"] == "PASS"


# --- 10. 专业 workflow 层自动修复 (确定性) ---

def test_workflow_autonomous_repair(tmp_path):
    """完整 workflow: Developer 生成坏代码 → 内置 pytest FAIL → 自动 repair → 全链 COMPLETED。"""
    ensure_professional_agents(tmp_path)

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        bad_code = ("def add(a, b):\n    return a - b\n\ndef subtract(a, b):\n    return a + b\n\n"
                    "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    return a / b\n")
        good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                     "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                     "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")
        content = {
            "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
            "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
            "software_developer": None,  # 动态
            "qa_engineer": "def test_add():\n    assert True\n",
        }[role]
        def fn(input_data):
            if role == "software_developer":
                # 第一次坏, 修复后好 (经 repair_fn)
                code = input_data.get("_code", bad_code)
                ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
                return {"ok": True, "output": {"content": code}, "patch_text": "",
                        "artifact_type": "code_change", "verification": ver, "content": code}
            return {"ok": True, "output": {"content": content}, "patch_text": "",
                    "artifact_type": "document", "verification": {"result": "PASS"}}
        return fn

    def dev_repair(failed_artifact, verification, ctx):
        good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                     "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                     "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")
        ver = verify_code_with_pytest(good_code, BUILTIN_CALC_TESTS)
        return {"ok": ver["status"] == "PASS", "output": {"content": good_code},
                "patch_text": "", "artifact_type": "code_change", "verification": ver,
                "content": good_code}

    from factory_console.professional_workflow import build_developer_repair_fn as _bdr
    # 用 monkeypatch 注入确定性 repair (真实 codex repair 在 real E2E)
    import factory_console.professional_workflow as _pw
    _orig = _pw.build_developer_repair_fn
    _pw.build_developer_repair_fn = lambda root, idea, arch: dev_repair
    try:
        result = run_professional_workflow(str(tmp_path), idea="calc", executor_factory=factory,
                                           max_repair=1)
    finally:
        _pw.build_developer_repair_fn = _orig
    assert result["state"] == "COMPLETED", result.get("failure")
    dev = result["runs"]["software_developer"]
    assert dev["state"] == "COMPLETED"
