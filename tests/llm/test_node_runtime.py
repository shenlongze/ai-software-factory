"""S2: Node Runtime — Node 定义 + NodeRun 状态机 + Executor + Artifact 集成。

覆盖 7 个 Acceptance Test:
1. Node Definition 注册/读取
2. NodeRun 生命周期 (PENDING→RUNNING→VERIFYING→COMPLETED)
3. 非法转换拒绝
4. Artifact 生产 (artifact.node_run_id 正确)
5. Verification (PASS→COMPLETED / FAIL→FAILED)
6. Executor 集成 (真实 executor_fn)
7. Audit 追踪 (history + audit 事件)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.node_runtime import (  # noqa: E402
    register_node, get_node, list_nodes,
    create_node_run, get_node_run, list_node_runs,
    transition_node_run, execute_node_run,
    NodeError, NODERUN_STATES,
)
from factory_console.artifact_lifecycle import (  # noqa: E402
    get_artifact, artifact_state,
)


def _node(root, **kw):
    return register_node(
        str(root), node_id=kw.get("node_id", "gen-code"),
        name=kw.get("name", "生成代码"), node_type=kw.get("node_type", "engineering"),
        input_contract=kw.get("input_contract", {"project_id": "str", "prompt": "str"}),
        output_contract=kw.get("output_contract", {"artifact_type": "code_change"}),
        execution_policy=kw.get("execution_policy", {"budget": {"max_time": 60}}),
    )


def _ok_executor(input_data):
    return {"ok": True, "output": {"note": "generated"}, "patch_text": "diff --git a/x b/x\n",
            "artifact_type": "code_change",
            "verification": {"result": "PASS", "tests": 1}}


def _fail_executor(input_data):
    return {"ok": False, "error": "executor exploded"}


def _verify_fail_executor(input_data):
    return {"ok": True, "output": {}, "patch_text": "diff",
            "artifact_type": "code_change",
            "verification": {"result": "FAIL", "error": "tests failed"}}


# --- Test 1: Node Definition ---

def test_node_definition_register_and_read(tmp_path):
    node = _node(tmp_path)
    assert node["node_id"] == "gen-code"
    assert node["type"] == "engineering"
    loaded = get_node(str(tmp_path), "gen-code")
    assert loaded["input_contract"]["project_id"] == "str"
    assert loaded["output_contract"]["artifact_type"] == "code_change"
    assert loaded["execution_policy"]["budget"]["max_time"] == 60
    # list
    assert any(n["node_id"] == "gen-code" for n in list_nodes(str(tmp_path)))


def test_node_missing_raises(tmp_path):
    with pytest.raises(NodeError):
        create_node_run(str(tmp_path), "ghost-node")


# --- Test 2: NodeRun lifecycle ---

def test_node_run_full_lifecycle(tmp_path):
    _node(tmp_path)
    run = create_node_run(str(tmp_path), "gen-code", input_data={"prompt": "hi"})
    assert run["state"] == "PENDING"
    assert run["node_id"] == "gen-code"
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_ok_executor,
                            executor_name="test-exec", artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    # history 完整
    states = [h["to"] for h in done["history"]]
    assert states == ["PENDING", "RUNNING", "VERIFYING", "COMPLETED"]
    assert done["started_at"] and done["completed_at"]
    assert done["executor"] == "test-exec"


# --- Test 3: Invalid transitions ---

def test_invalid_transitions_rejected(tmp_path):
    _node(tmp_path)
    run = create_node_run(str(tmp_path), "gen-code")
    rid = run["run_id"]
    bad = [
        ("PENDING", "COMPLETED"),
        ("PENDING", "VERIFYING"),
        ("RUNNING", "COMPLETED"),
        ("COMPLETED", "RUNNING"),
        ("FAILED", "RUNNING"),
    ]
    for frm, to in bad:
        # 构造独立 run, 先推到 frm (若可能)
        r2 = create_node_run(str(tmp_path), "gen-code")
        r2id = r2["run_id"]
        if frm == "RUNNING":
            transition_node_run(str(tmp_path), r2id, "RUNNING")
        elif frm == "COMPLETED":
            transition_node_run(str(tmp_path), r2id, "RUNNING")
            transition_node_run(str(tmp_path), r2id, "VERIFYING")
            transition_node_run(str(tmp_path), r2id, "COMPLETED")
        elif frm == "FAILED":
            transition_node_run(str(tmp_path), r2id, "RUNNING")
            transition_node_run(str(tmp_path), r2id, "FAILED")
        try:
            transition_node_run(str(tmp_path), r2id, to)
            assert False, f"非法转换未拒绝: {frm}→{to}"
        except NodeError:
            pass


# --- Test 4: Artifact production ---

def test_node_run_produces_artifact(tmp_path):
    _node(tmp_path)
    run = create_node_run(str(tmp_path), "gen-code")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_ok_executor,
                            executor_name="exec", artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    aid = done["artifact_id"]
    assert aid, "NodeRun 必须产出 Artifact"
    art = get_artifact(str(tmp_path), aid)
    assert art is not None
    assert art["node_run_id"] == run["run_id"], "Artifact 必须引用 NodeRun"
    # 反向查询: NodeRun → Artifact
    assert done["artifact_id"] == aid
    # Artifact 状态 GENERATED (S1 Lifecycle 管理)
    assert artifact_state(str(tmp_path), aid) == "GENERATED"


# --- Test 5: Verification ---

def test_verification_pass_completes(tmp_path):
    _node(tmp_path)
    run = create_node_run(str(tmp_path), "gen-code")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_ok_executor,
                            executor_name="exec", artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    assert done["verification"]["result"] == "PASS"


def test_verification_fail_fails_run(tmp_path):
    _node(tmp_path)
    run = create_node_run(str(tmp_path), "gen-code")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_verify_fail_executor,
                            executor_name="exec", artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    assert done["verification"]["result"] == "FAIL"
    assert "tests failed" in done["failure_reason"]


def test_executor_failure_fails_run(tmp_path):
    _node(tmp_path)
    run = create_node_run(str(tmp_path), "gen-code")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_fail_executor,
                            executor_name="exec", artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    assert "executor exploded" in done["failure_reason"]
    # FAILED 无 artifact (未产出)
    assert done.get("artifact_id") is None


# --- Test 6: Executor integration ---

def test_executor_contract_reused(tmp_path):
    """真实 executor_fn 契约: input → {ok, output, patch_text} → Artifact。"""
    _node(tmp_path)
    seen = {}

    def spy_executor(input_data):
        seen["input"] = input_data
        return _ok_executor(input_data)

    run = create_node_run(str(tmp_path), "gen-code", input_data={"prompt": "build X"})
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=spy_executor,
                            executor_name="spy", artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    assert seen["input"]["prompt"] == "build X"


# --- Test 7: Audit ---

def test_node_run_auditable(tmp_path):
    _node(tmp_path)
    run = create_node_run(str(tmp_path), "gen-code")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_ok_executor,
                            executor_name="exec", artifact_root=str(tmp_path))
    # history 含 actor + at
    for h in done["history"]:
        assert "actor" in h and "at" in h
    # audit 事件落盘
    ev_path = tmp_path / "audit" / "audit_events.json"
    assert ev_path.exists()
    import json
    evs = json.loads(ev_path.read_text(encoding="utf-8"))
    assert any("NODE_RUN_" in e.get("event_type", "") for e in evs)
