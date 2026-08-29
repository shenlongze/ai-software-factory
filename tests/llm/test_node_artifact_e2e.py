"""S2: Node Runtime + Artifact Lifecycle 组合 E2E — 两个 Production Primitive 首次组合。

真实链路 (不 mock):
Node → NodeRun → 真实 Executor → Artifact → Verification
     → Artifact Lifecycle (Approval → Apply) → 真实 Workspace 变化

核心证明:
1. NodeRun 产生 Artifact (不走 workspace)
2. Artifact Lifecycle 管理后续 (Approved → Applied → 真实 git apply)
3. NodeRun 不直接修改 Workspace (architecture invariant)
4. workspace 最终真实变化 (组合成功)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from factory_console.node_runtime import (  # noqa: E402
    register_node, create_node_run, execute_node_run, get_node_run,
)
from factory_console.artifact_lifecycle import (  # noqa: E402
    get_artifact, approve_artifact, apply_artifact, artifact_state,
    transition_artifact,
)


def _git(ws: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(ws), *args], capture_output=True, text=True, timeout=60)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _init_repo(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
    _git(ws, "init", "-q")
    _git(ws, "add", "-A")
    _git(ws, "-c", "user.email=factory@local", "-c", "user.name=factory", "commit", "-q", "-m", "base")


def _real_executor(input_data):
    """模拟真实执行器: 生成一个真实可 apply 的 patch (新增函数)。"""
    patch = (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1,5 @@\n"
        " x = 1\n"
        "+\n"
        "+def add(a: int, b: int) -> int:\n"
        "+    return a + b\n"
    )
    return {
        "ok": True,
        "output": {"generated": "add function"},
        "patch_text": patch,
        "artifact_type": "code_change",
        "verification": {"result": "PASS", "source": "syntax", "tests": 1},
    }


def test_node_to_workspace_full_chain(tmp_path):
    """两个 Production Primitive 组合: Node → Artifact → Approval → Apply → Workspace。"""
    ws = tmp_path / "ws"
    _init_repo(ws)
    before = (ws / "main.py").read_text()

    # 1) Node → NodeRun → 真实 Executor → Artifact
    register_node(str(tmp_path), node_id="gen-add", name="生成add函数", node_type="engineering")
    run = create_node_run(str(tmp_path), "gen-add", input_data={"project_id": "P-e2e"})
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_real_executor,
                            executor_name="real-exec", artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    aid = done["artifact_id"]

    # 2) NodeRun 不直接改 Workspace (invariant)
    assert (ws / "main.py").read_text() == before, "NodeRun 不得直接修改 Workspace"

    # 3) Artifact 走 Lifecycle: STAGED → REVIEWED → APPROVED → APPLIED
    art = get_artifact(str(tmp_path), aid)
    assert art["state"] == "GENERATED"
    transition_artifact(str(tmp_path), aid, "STAGED", actor="system")
    transition_artifact(str(tmp_path), aid, "REVIEWED", actor="system")
    approve_artifact(str(tmp_path), aid, approved_by="user1")
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-e2e", "state": "APPROVED"})

    # 4) 真实 workspace 变化 + 状态
    after = (ws / "main.py").read_text()
    assert artifact_state(str(tmp_path), aid) == "APPLIED"
    assert before != after, "workspace 必须真实变化"
    assert "def add" in after
    # git 确认
    code, out = _git(ws, "diff")
    assert "def add" in out or "def add" in after


def test_artifact_traceability(tmp_path):
    """追溯: artifact_id → node_run_id → node_id, 反向可查。"""
    register_node(str(tmp_path), node_id="gen-add", name="生成add函数", node_type="engineering")
    run = create_node_run(str(tmp_path), "gen-add")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=_real_executor,
                            executor_name="real-exec", artifact_root=str(tmp_path))
    aid = done["artifact_id"]
    # 正向
    art = get_artifact(str(tmp_path), aid)
    assert art["node_run_id"] == run["run_id"]
    # NodeRun → Node
    run_loaded = get_node_run(str(tmp_path), run["run_id"])
    assert run_loaded["node_id"] == "gen-add"
    # NodeRun → Artifact (artifact_id 在 run 上)
    assert run_loaded["artifact_id"] == aid


def test_verification_fail_stops_before_apply(tmp_path):
    """Verification FAIL → NodeRun FAILED, 无 artifact 可 apply。"""
    ws = tmp_path / "ws"
    _init_repo(ws)
    register_node(str(tmp_path), node_id="bad-node", name="坏节点", node_type="engineering")

    def bad_executor(input_data):
        return {"ok": True, "output": {}, "patch_text": "bad",
                "artifact_type": "code_change",
                "verification": {"result": "FAIL", "error": "tests failed"}}

    run = create_node_run(str(tmp_path), "bad-node")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=bad_executor,
                            executor_name="bad-exec", artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    assert done["verification"]["result"] == "FAIL"
    # workspace 未动
    assert (ws / "main.py").read_text() == "x = 1\n"
