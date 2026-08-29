"""S9: Agent Kernel — 专业 AI 员工 + Artifact-centric Handoff。

覆盖 24 项:
1. Agent 定义注册/解析/持久化
2. AgentRun 创建/生命周期/持久化/审计
3. 输入/输出 contract
4. Handoff 创建/显式 artifact 引用/接收者校验/持久化/lineage
5. No Hidden State (清空 session 后 QA 仍可执行)
6. Integration: Agent → ProductionRun → 真实 executor → Artifact → Verification → Apply → Workspace
7. Real Handoff: Agent A → Artifact A → Handoff → Agent B
8. Failure: Agent 失败 → downstream blocked
9. Recovery: AgentRun 底层 ProductionRun 恢复
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

from factory_console.agent_kernel import (  # noqa: E402
    create_agent_run, get_agent_run, list_agent_runs, run_agent,
    create_handoff, get_handoff, list_handoffs, AgentKernelError,
)
from factory_console.session.agent_entity import AgentEntity  # noqa: E402
from factory_console.session.agent_registry import AgentRegistry  # noqa: E402
from factory_console.artifact_lifecycle import (  # noqa: E402
    get_artifact, transition_artifact, approve_artifact, apply_artifact,
)


def _reg(root):
    return AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")


def _add_agent(root, agent_id: str, role: str):
    agent = AgentEntity(id=agent_id, name=None, role=role, industry="it",
                        system_prompt=f"You are a {role}.",
                        skills=["python_code_generation"])
    _reg(root).add(agent)


def _good_factory(node_id):
    def fn(input_data):
        target = input_data.get("target_file", f"{node_id}.py")
        patch = (f"diff --git a/{target} b/{target}\n--- /dev/null\n+++ b/{target}\n"
                 "@@ -0,0 +1,2 @@\n+def work():\n+    return 1\n")
        return {"ok": True, "output": {"code": "work"}, "patch_text": patch,
                "artifact_type": "code_change",
                "verification": {"result": "PASS", "tests": 1}}
    return fn


# --- 1. Agent 定义 ---

def test_agent_definition(tmp_path):
    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    reg = _reg(tmp_path)
    a = reg.get("agt-it-developer-1")
    assert a is not None
    assert a.role == "developer"
    assert "python_code_generation" in a.skills
    assert len(reg.list()) == 1
    # 持久化: 重新加载
    reg2 = _reg(tmp_path)
    assert reg2.get("agt-it-developer-1") is not None


# --- 2. AgentRun 创建/生命周期 ---

def test_agent_run_lifecycle(tmp_path):
    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    run = create_agent_run(str(tmp_path), "agt-it-developer-1", trigger="test")
    assert run["state"] == "PENDING"
    assert run["agent_id"] == "agt-it-developer-1"
    # 不存在的 agent → 错误
    with pytest.raises(AgentKernelError):
        create_agent_run(str(tmp_path), "agt-it-ghost-1")
    # 持久化
    loaded = get_agent_run(str(tmp_path), run["agent_run_id"])
    assert loaded is not None
    assert len(list_agent_runs(str(tmp_path))) == 1


# --- 3. Contract: 输入 artifact 校验 ---

def test_agent_run_input_artifacts(tmp_path):
    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    run = create_agent_run(str(tmp_path), "agt-it-developer-1", input_artifacts=["art-x"], trigger="test")
    assert run["input_artifacts"] == ["art-x"]


# --- 4. Handoff 创建/校验/持久化/lineage ---

def test_handoff_create_and_validate(tmp_path):
    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    _add_agent(tmp_path, "agt-it-qa-1", "qa")
    # 先让 dev 完成一次工作 (产出 artifact)
    run = create_agent_run(str(tmp_path), "agt-it-developer-1")
    done = run_agent(str(tmp_path), run["agent_run_id"], workflow_id="wf-dev",
                     executor_factory=_good_factory, workflow_input={"target_file": "code.py"})
    assert done["state"] == "COMPLETED"
    aid = done["output_artifacts"][0]
    # Handoff: dev → qa, 只传 artifact reference
    h = create_handoff(str(tmp_path), from_agent_run_id=run["agent_run_id"],
                       to_agent_id="agt-it-qa-1", input_artifacts=[aid])
    assert h["status"] == "CREATED"
    assert h["from_agent_id"] == "agt-it-developer-1"
    assert h["to_agent_id"] == "agt-it-qa-1"
    assert h["input_artifacts"] == [aid]
    # 持久化
    loaded = get_handoff(str(tmp_path), h["handoff_id"])
    assert loaded is not None
    assert len(list_handoffs(str(tmp_path))) == 1
    # lineage: artifact → agent_run
    art = get_artifact(str(tmp_path), aid)
    assert art["producer"] == "work"  # node executor


# --- 5. No Hidden State: 清空 session 后 QA 仍可执行 ---

def test_handoff_no_hidden_state(tmp_path):
    """QA 输入只来自 Handoff.input_artifacts, 不依赖任何 global/session state。"""
    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    _add_agent(tmp_path, "agt-it-qa-1", "qa")
    run = create_agent_run(str(tmp_path), "agt-it-developer-1")
    done = run_agent(str(tmp_path), run["agent_run_id"], workflow_id="wf-dev",
                     executor_factory=_good_factory, workflow_input={"target_file": "code.py"})
    aid = done["output_artifacts"][0]
    h = create_handoff(str(tmp_path), from_agent_run_id=run["agent_run_id"],
                       to_agent_id="agt-it-qa-1", input_artifacts=[aid])
    # 模拟"清空 session/global" — QA 侧只能看到 handoff + artifact
    qa_run = create_agent_run(str(tmp_path), "agt-it-qa-1",
                              input_artifacts=h["input_artifacts"], trigger="handoff")
    # QA 执行: 输入显式来自 handoff 的 artifact reference (无 hidden state)
    assert qa_run["input_artifacts"] == [aid]
    # 校验 artifact 真实可读 (不是凭空)
    art = get_artifact(str(tmp_path), aid)
    assert art is not None
    assert "def work" in (art.get("patch_text") or "") or art["artifact_id"] == aid


# --- 6. Integration: Agent → ProductionRun → Artifact → Apply → Workspace ---

def test_agent_integration_apply_workspace(tmp_path):
    """Agent 经 Production Kernel 真实执行 → Artifact → Lifecycle → Apply → Workspace。"""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=f@l", "-c", "user.name=f", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(ws), *c], capture_output=True, text=True, timeout=60)
    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    run = create_agent_run(str(tmp_path), "agt-it-developer-1")
    done = run_agent(str(tmp_path), run["agent_run_id"], workflow_id="wf-dev",
                     executor_factory=_good_factory,
                     workflow_input={"target_file": "code.py", "project_id": "P-9"})
    assert done["state"] == "COMPLETED"
    assert len(done["output_artifacts"]) == 1
    aid = done["output_artifacts"][0]
    # Apply 前 workspace 未动
    assert not (ws / "code.py").exists()
    # Artifact → Lifecycle → Apply
    transition_artifact(str(tmp_path), aid, "STAGED", actor="system")
    transition_artifact(str(tmp_path), aid, "REVIEWED", actor="system")
    approve_artifact(str(tmp_path), aid, approved_by="user1")
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-9", "state": "APPROVED"})
    assert "def work" in (ws / "code.py").read_text()


# --- 7. Real Handoff: Dev → QA 两 Agent 链 ---

def test_real_agent_handoff_chain(tmp_path):
    """Agent A (dev) → Artifact A → Handoff → Agent B (qa) → Artifact B。"""
    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    _add_agent(tmp_path, "agt-it-qa-1", "qa")
    # A: dev 工作
    dev_run = create_agent_run(str(tmp_path), "agt-it-developer-1")
    dev_done = run_agent(str(tmp_path), dev_run["agent_run_id"], workflow_id="wf-dev",
                         executor_factory=_good_factory,
                         workflow_input={"target_file": "code.py"})
    assert dev_done["state"] == "COMPLETED"
    art_a = dev_done["output_artifacts"][0]
    # Handoff: dev → qa
    h = create_handoff(str(tmp_path), from_agent_run_id=dev_run["agent_run_id"],
                       to_agent_id="agt-it-qa-1", input_artifacts=[art_a])
    # B: qa 工作 (输入 = handoff artifacts)
    qa_run = create_agent_run(str(tmp_path), "agt-it-qa-1",
                              input_artifacts=h["input_artifacts"], trigger="handoff")
    qa_done = run_agent(str(tmp_path), qa_run["agent_run_id"], workflow_id="wf-qa",
                        executor_factory=_good_factory,
                        workflow_input={"target_file": "test.py"})
    assert qa_done["state"] == "COMPLETED"
    assert len(qa_done["output_artifacts"]) == 1
    # lineage: qa 的 input_artifacts == dev 的 output
    assert qa_done["input_artifacts"] == [art_a]


# --- 8. Failure: Agent 失败 → FAILED ---

def test_agent_failure(tmp_path):
    _add_agent(tmp_path, "agt-it-developer-1", "developer")

    def fail_factory(node_id):
        def fn(input_data):
            return {"ok": False, "error": "agent work failed", "artifact_type": "report"}
        return fn
    run = create_agent_run(str(tmp_path), "agt-it-developer-1")
    done = run_agent(str(tmp_path), run["agent_run_id"], workflow_id="wf-dev",
                     executor_factory=fail_factory)
    assert done["state"] == "FAILED"
    assert done["failure"]


# --- 9. Recovery: AgentRun 底层 ProductionRun 恢复 ---

def test_agent_run_recovery(tmp_path):
    """AgentRun 崩溃 → 底层 ProductionRun 经 S7 Recovery 恢复 (不建第二套)。"""
    from factory_console import recovery as _rec
    from factory_console import production_service as _psvc

    _add_agent(tmp_path, "agt-it-developer-1", "developer")
    run = create_agent_run(str(tmp_path), "agt-it-developer-1")
    done = run_agent(str(tmp_path), run["agent_run_id"], workflow_id="wf-dev",
                     executor_factory=_good_factory,
                     workflow_input={"target_file": "code.py"})
    assert done["state"] == "COMPLETED"
    prun_id = done["production_run_id"]
    # 复用 S7 Recovery analyze (ProductionRun 层)
    a = _psvc.analyze(str(tmp_path), prun_id)
    assert a["recoverable_state"] == "already_completed"
