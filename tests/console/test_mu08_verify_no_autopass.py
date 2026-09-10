"""MU-08: 切断 "Execution success → Verification PASS" 自动推导。

契约 (docs/architecture/OS_CORE_SSOT_CONTRACT.md §2/§3/§7):
- Execution success (exit_code==0) ≠ Verification PASS
- 缺省 / 无显式验证 → Verification = UNKNOWN (诚实缺省)
- 只有显式 verify (method + result) 才可 PASS; 真实验证路径不得被破坏

三个 Case:
  A. executor exit_code==0 无显式验证 → verification == UNKNOWN (非 PASS)
  B. executor exit_code!=0          → verification != PASS
  C. 显式 PASS / 真实验证链          → 保持 PASS, release gate 仍可 GATED
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from factory_console.production_run import (  # noqa: E402
    build_executor_factory,
    create_production_run,
    execute_production_run,
    register_workflow,
)
from factory_console.node_runtime import (  # noqa: E402
    create_node_run,
    finalize_node_run,
    get_node_run,
    register_node,
)
from factory_console.verification_domain import get_verification  # noqa: E402

_PATCH = ("diff --git a/main.py b/main.py\n--- a/main.py\n+++ b/main.py\n"
          "@@ -1 +1,4 @@\n x = 1\n+\n+def add(a, b):\n+    return a + b\n")


# ---------------------------------------------------------------- Case A (production_run 适配层)

def test_pr_executor_success_is_not_pass(tmp_path: Path, monkeypatch) -> None:
    """production_run._fn: executor exit_code==0 → verification UNKNOWN (非 PASS)。"""
    import factory_console.production_run as pr

    class _FakeReg:
        def get(self, name):  # noqa: ANN001
            return {"name": name}

    monkeypatch.setattr(pr, "_BUILD_REGISTRY", lambda root: _FakeReg())
    monkeypatch.setattr(
        "factory_console.external_executor.executor.run",
        lambda adapter, prompt, project_dir, agent="", timeout=None: {
            "exit_code": 0, "output": "done", "error": "", "command": "mock"},
    )
    fn = build_executor_factory(str(tmp_path))("codex")
    out = fn({"prompt": "do it", "project_dir": str(tmp_path), "artifact_type": "report"})
    assert out["ok"] is True, "执行成功"
    assert out["verification"]["result"] == "UNKNOWN", "执行成功不得隐式 PASS"
    assert out["verification"]["result"] != "PASS"


# ---------------------------------------------------------------- Case B (执行失败)

def test_pr_executor_failure_not_pass(tmp_path: Path, monkeypatch) -> None:
    """production_run._fn: executor exit_code!=0 → verification != PASS。"""
    import factory_console.production_run as pr

    class _FakeReg:
        def get(self, name):  # noqa: ANN001
            return {"name": name}

    monkeypatch.setattr(pr, "_BUILD_REGISTRY", lambda root: _FakeReg())
    monkeypatch.setattr(
        "factory_console.external_executor.executor.run",
        lambda adapter, prompt, project_dir, agent="", timeout=None: {
            "exit_code": 1, "output": "", "error": "boom", "command": "mock"},
    )
    fn = build_executor_factory(str(tmp_path))("codex")
    out = fn({"prompt": "do it", "project_dir": str(tmp_path), "artifact_type": "report"})
    assert out["ok"] is False
    assert out["verification"]["result"] != "PASS"


# ---------------------------------------------------------------- Case A2 (node_runtime 缺省)

def _exec_ok_no_verification(node_id: str):
    def fn(input_data):  # noqa: ANN001
        return {"ok": True, "output": {"code": "add"}, "patch_text": _PATCH,
                "artifact_type": "code_change"}  # 真实 executor 只报执行完成, 无验证
    return fn


def test_node_runtime_missing_verification_is_unknown(tmp_path: Path) -> None:
    """node_runtime: 无显式验证 → ver-* SSOT 落盘 UNKNOWN (非 PASS); run FAILED。"""
    register_workflow(str(tmp_path), workflow_id="wf-a", name="wf",
                      nodes=[{"node_id": "n1", "name": "N1"}])
    run = create_production_run(str(tmp_path), "wf-a")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_exec_ok_no_verification,
                                  artifact_root=str(tmp_path))
    assert done["state"] == "FAILED", "UNKNOWN 不得视为 COMPLETED"
    nr = get_node_run(str(tmp_path), done["node_runs"][0]["run_id"])
    assert nr["verification"]["status"] == "UNKNOWN"
    assert nr["verification"]["status"] != "PASS"
    v = get_verification(str(tmp_path), nr["verification"]["verification_id"])
    assert v is not None and v["status"] == "UNKNOWN", "ver-* SSOT 必须为 UNKNOWN"


# ---------------------------------------------------------------- Case C (显式验证不被破坏)

def _exec_explicit_pass(node_id: str):
    def fn(input_data):  # noqa: ANN001
        return {"ok": True, "output": {"code": "add"}, "patch_text": _PATCH,
                "artifact_type": "code_change",
                "verification": {"result": "PASS", "method": "pytest -q", "tests": 1}}
    return fn


def test_explicit_verification_pass_preserved(tmp_path: Path) -> None:
    """显式 verification PASS → 保持 PASS, run COMPLETED (未误伤真实验证)。"""
    register_workflow(str(tmp_path), workflow_id="wf-c", name="wf",
                      nodes=[{"node_id": "n1", "name": "N1"}])
    run = create_production_run(str(tmp_path), "wf-c")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_exec_explicit_pass,
                                  artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    nr = get_node_run(str(tmp_path), done["node_runs"][0]["run_id"])
    assert nr["verification"]["status"] == "PASS"


def test_real_verification_chain_release_gated(tmp_path: Path) -> None:
    """真实验证链 (finalize + verify_pytest PASS + EVD) → release gate GATED (未破坏)。"""
    from factory_console.external_executor.executor import record_invocation
    from factory_console.verification import verify_pytest
    from factory_console import release_truth as rt

    root = tmp_path / "factory"
    register_node(root, node_id="task-execution", name="t", node_type="task-execution")
    proj = root / "proj-ok"
    proj.mkdir(parents=True)
    (proj / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    run = create_node_run(root, "task-execution", task_id="TASK-mu08", trigger="chain")
    rec = record_invocation(root, executor_id="hermes", mode="blackbox", host_agent="",
                            prompt="TASK-mu08", project_dir=str(proj), exit_code=0,
                            output="ok", error="", command="hermes", duration_ms=10,
                            task_id="TASK-mu08", task_run_id=run["run_id"])
    v = verify_pytest(proj)
    out = finalize_node_run(root, run["run_id"], success=True, exs_id=rec["result_id"],
                            output=str(v.get("stdout", "")), actor="test",
                            verification={"method": "pytest -q",
                                          "result": "pass" if v.get("status") == "PASS" else "fail"})
    assert out["verification"]["status"] == "PASS"
    rel = rt.create_release(root, task_run_id=run["run_id"], exs_id=rec["result_id"])
    g = rt.gate_release(root, rel["release_id"])
    assert g["status"] == "GATED"
    assert g["gate"]["allowed"] is True
