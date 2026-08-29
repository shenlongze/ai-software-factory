"""S3: ProductionRun / Workflow — 串行 DAG + Artifact binding + 失败语义。

覆盖 12 个 Acceptance Test:
1. Workflow 创建 | 2. ProductionRun 创建 | 3. 串行 A→B→C
4. Dependency 强制 | 5. Artifact A→B input | 6. Artifact B→C input
7. 失败→依赖 Node BLOCKED | 8. ProductionRun failure 聚合
9. Audit/Evidence trace | 10. 真实 Executor E2E | 11. 真实 Apply | 12. 真实 Workspace
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_run import (  # noqa: E402
    register_workflow, get_workflow, create_production_run, get_production_run,
    list_production_runs, execute_production_run, ProductionRunError,
)
from factory_console.node_runtime import get_node_run  # noqa: E402
from factory_console.artifact_lifecycle import get_artifact  # noqa: E402


def _wf_nodes():
    return [
        {"node_id": "gen-code", "name": "生成函数", "type": "engineering"},
        {"node_id": "gen-test", "name": "生成测试", "type": "engineering",
         "depends_on": ["gen-code"], "input_binding": {"code_artifact": "artifact:gen-code"}},
        {"node_id": "run-verify", "name": "运行验证", "type": "qa",
         "depends_on": ["gen-test"], "input_binding": {"test_artifact": "artifact:gen-test"}},
    ]


def _executor_factory(node_id):
    def fn(input_data):
        if node_id == "gen-code":
            patch = (
                "diff --git a/main.py b/main.py\n--- a/main.py\n+++ b/main.py\n"
                "@@ -1 +1,5 @@\n x = 1\n+\n+def add(a: int, b: int) -> int:\n+    return a + b\n"
            )
            return {"ok": True, "output": {"code": "add function"}, "patch_text": patch,
                    "artifact_type": "code_change",
                    "verification": {"result": "PASS", "tests": 1}}
        if node_id == "gen-test":
            patch = (
                "diff --git a/test_main.py b/test_main.py\n--- /dev/null\n+++ b/test_main.py\n"
                "@@ -0,0 +1,4 @@\n+import main\n+\n+def test_add():\n+    assert main.add(2, 3) == 5\n"
            )
            return {"ok": True, "output": {"test": "test_add"}, "patch_text": patch,
                    "artifact_type": "code_change",
                    "verification": {"result": "PASS", "tests": 1}}
        # run-verify: 引用下游输入
        assert input_data.get("test_artifact"), "run-verify 必须接收 gen-test 的 artifact"
        return {"ok": True, "output": {"verified": True}, "patch_text": "",
                "artifact_type": "report",
                "verification": {"result": "PASS", "tests": 3}}
    return fn


def _bad_executor_factory(node_id):
    def fn(input_data):
        if node_id in ("gen-code", "a"):
            return {"ok": False, "error": f"{node_id} exploded"}
        return {"ok": True, "output": {}, "patch_text": "",
                "artifact_type": "report", "verification": {"result": "PASS"}}
    return fn


# --- Test 1/2: Workflow + ProductionRun ---

def test_workflow_definition(tmp_path):
    wf = register_workflow(str(tmp_path), workflow_id="wf-1", name="生成+测试+验证",
                           project_id="P-1", nodes=_wf_nodes())
    assert wf["workflow_id"] == "wf-1"
    loaded = get_workflow(str(tmp_path), "wf-1")
    assert len(loaded["nodes"]) == 3
    # 非法依赖
    with pytest.raises(ProductionRunError):
        register_workflow(str(tmp_path), workflow_id="wf-bad", name="bad",
                          nodes=[{"node_id": "a"}, {"node_id": "b", "depends_on": ["ghost"]}])


def test_production_run_create(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1", input_data={"project_id": "P-1"})
    assert run["state"] == "PENDING"
    assert run["workflow_id"] == "wf-1"
    loaded = get_production_run(str(tmp_path), run["run_id"])
    assert loaded["run_id"] == run["run_id"]
    assert len(list_production_runs(str(tmp_path))) == 1


# --- Test 3: 串行 A→B→C ---

def test_serial_execution(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id="P-1",
                      nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_executor_factory, artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    node_states = {n["node_id"]: n["state"] for n in done["node_runs"]}
    assert node_states == {"gen-code": "COMPLETED", "gen-test": "COMPLETED", "run-verify": "COMPLETED"}
    # 3 个 artifacts
    assert len(done["artifacts"]) == 3


# --- Test 4: Dependency 强制 (B 不能先于 A) ---

def test_dependency_enforced(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_executor_factory, artifact_root=str(tmp_path))
    # 执行顺序: gen-code 先于 gen-test 先于 run-verify
    order = [n["node_id"] for n in done["node_runs"]]
    assert order.index("gen-code") < order.index("gen-test") < order.index("run-verify")


# --- Test 5/6: Artifact binding ---

def test_artifact_binding(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_executor_factory, artifact_root=str(tmp_path))
    # NodeRun gen-test 的输入含 code_artifact (来自 gen-code 的 artifact)
    for nr in done["node_runs"]:
        if nr["node_id"] == "gen-test":
            run_rec = get_node_run(str(tmp_path), nr["run_id"])
            assert run_rec["input"]["code_artifact"] == done["artifacts"][0], \
                "gen-test 输入必须来自 gen-code 的 artifact"
        if nr["node_id"] == "run-verify":
            run_rec = get_node_run(str(tmp_path), nr["run_id"])
            assert run_rec["input"]["test_artifact"] == done["artifacts"][1], \
                "run-verify 输入必须来自 gen-test 的 artifact"


def test_no_hidden_state(tmp_path):
    """Node B 输入必须可追溯到 Artifact A (无 hidden state)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_executor_factory, artifact_root=str(tmp_path))
    # 追溯: gen-test input.code_artifact → artifact_id → gen-code
    nr_recs = {n["node_id"]: n for n in done["node_runs"]}
    gen_test = get_node_run(str(tmp_path), nr_recs["gen-test"]["run_id"])
    art_id = gen_test["input"]["code_artifact"]
    art = get_artifact(str(tmp_path), art_id)
    assert art["node_run_id"] == nr_recs["gen-code"]["run_id"], \
        "artifact 必须追溯到产出它的 NodeRun"


# --- Test 7/8: 失败语义 ---

def test_failure_blocks_dependents(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_bad_executor_factory, artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    assert done["failure"], "必须有失败原因"
    # gen-code FAILED, 后续不执行
    assert len(done["node_runs"]) == 1  # 只有 gen-code 执行了
    assert done["node_runs"][0]["state"] == "FAILED"


def test_dependency_failure_blocks_not_runs(tmp_path):
    """A FAIL → B/C 不执行 (BLOCKED 或 NOT_RUN)。"""
    nodes = [
        {"node_id": "a", "name": "A"},
        {"node_id": "b", "name": "B", "depends_on": ["a"]},
    ]
    register_workflow(str(tmp_path), workflow_id="wf-2", name="wf2", nodes=nodes)
    run = create_production_run(str(tmp_path), "wf-2")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_bad_executor_factory, artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    # b 未执行 (不在 node_runs 或 BLOCKED)
    assert all(n["node_id"] != "b" or n["state"] == "BLOCKED" for n in done["node_runs"])


# --- Test 9: Audit ---

def test_production_run_auditable(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")
    execute_production_run(str(tmp_path), run["run_id"],
                           executor_factory=_executor_factory, artifact_root=str(tmp_path))
    loaded = get_production_run(str(tmp_path), run["run_id"])
    assert len(loaded["history"]) >= 3  # PENDING + RUNNING + COMPLETED
    import json
    ev_path = tmp_path / "audit" / "audit_events.json"
    assert ev_path.exists()
    evs = json.loads(ev_path.read_text(encoding="utf-8"))
    assert any("PRODUCTION_RUN_" in e.get("event_type", "") for e in evs)


# --- Test 10/11/12: 真实 E2E + Apply + Workspace ---

def test_real_e2e_apply_workspace(tmp_path):
    """完整: ProductionRun → 3 Node → Artifacts → Lifecycle → Apply → 真实 Workspace。"""
    import subprocess

    from factory_console.artifact_lifecycle import (
        transition_artifact, approve_artifact, apply_artifact, artifact_state,
    )

    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=f@l", "-c", "user.name=f", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(ws), *c], capture_output=True, text=True, timeout=60)

    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id="P-1",
                      nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")
    done = execute_production_run(str(tmp_path), run["run_id"],
                                  executor_factory=_executor_factory, artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"

    # Apply 前 workspace 未动 (Node 不直接写)
    assert (ws / "main.py").read_text() == "x = 1\n", "ProductionRun 不得直接改 Workspace"

    # 每个 artifact 走 Lifecycle → Apply
    for aid in done["artifacts"]:
        art = get_artifact(str(tmp_path), aid)
        if not art.get("patch_text"):
            continue
        transition_artifact(str(tmp_path), aid, "STAGED", actor="system")
        transition_artifact(str(tmp_path), aid, "REVIEWED", actor="system")
        approve_artifact(str(tmp_path), aid, approved_by="user1")
        apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                       approval={"approval_id": "apr-1", "state": "APPROVED"})
        assert artifact_state(str(tmp_path), aid) == "APPLIED"

    # 真实 Workspace 最终状态: 含代码 + 测试
    main_content = (ws / "main.py").read_text()
    test_content = (ws / "test_main.py").read_text() if (ws / "test_main.py").exists() else ""
    assert "def add" in main_content, "workspace 必须含生成的代码"
    assert "test_add" in test_content, "workspace 必须含生成的测试"
    # git 确认
    proc = subprocess.run(["git", "-C", str(ws), "status", "--short"],
                          capture_output=True, text=True, timeout=60)
    assert "main.py" in proc.stdout or "test_main.py" in proc.stdout
