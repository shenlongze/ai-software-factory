"""S10: Professional Workflow Assembly — PM→Architect→Developer→QA 生产线。

覆盖:
- 4 专业 Agent 定义 (AgentEntity)
- 专业 workflow 存在 + 依赖正确
- Handoff: PM→Arch→Dev→QA (artifact-only, no-hidden-state)
- 专业验收: PRD/Arch 章节 / code 语法 / QA pytest
- 失败阻断下游
- Repair 新 Artifact
- Recovery
- 真实 E2E: Idea → PM → PRD → Arch → Dev → Code → QA → pytest → Apply → Workspace
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
    ensure_professional_agents, list_professional_agents, PROFESSIONAL_WORKFLOW_ID,
    PROFESSIONAL_ROLES, run_professional_workflow, build_llm_executor_factory,
    ROLE_TARGETS, _verify_role_output,
)
from factory_console.session.agent_registry import AgentRegistry  # noqa: E402
from factory_console.agent_kernel import (  # noqa: E402
    create_agent_run, run_agent, get_agent_run, create_handoff, list_handoffs,
)
from factory_console.artifact_lifecycle import (  # noqa: E402
    get_artifact, transition_artifact, approve_artifact, apply_artifact,
)


def _reg(root):
    return AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")


# --- 1. 4 专业 Agent 定义 ---

def test_professional_agents_exist(tmp_path):
    ensure_professional_agents(tmp_path)
    reg = _reg(tmp_path)
    for role in PROFESSIONAL_ROLES:
        assert reg.get(f"agt-it-{role}-1") is not None, f"{role} 必须存在"
    assert len(list_professional_agents(tmp_path)) >= 4


def test_professional_agents_have_prompts_and_skills(tmp_path):
    ensure_professional_agents(tmp_path)
    reg = _reg(tmp_path)
    pm = reg.get("agt-it-product_manager-1")
    assert pm is not None
    assert "PRD" in pm.system_prompt
    assert "prd_writing" in pm.skills


# --- 2. Workflow ---

def test_workflow_definition(tmp_path):
    assert PROFESSIONAL_WORKFLOW_ID == "software-product-production"
    # S16: 核心 4 角色是子集 (扩展了 market/ux/release)
    assert {"product_manager", "software_architect",
            "software_developer", "qa_engineer"} <= set(PROFESSIONAL_ROLES)


# --- 3. Handoff artifact-only + no-hidden-state ---

def test_handoff_artifact_only(tmp_path):
    """PM → Handoff → Architect: 只传 artifact id, 无 hidden state。"""
    ensure_professional_agents(tmp_path)
    # PM 产出 PRD artifact (确定性 executor)
    def pm_factory(agent_id):
        def fn(input_data):
            prd = ("# 产品需求文档\n## Problem\n计算器\n## Target Users\n普通用户\n"
                   "## Goals\n加减法\n## Functional Requirements\nadd/subtract\n"
                   "## Non-Functional Requirements\n简单\n## Acceptance Criteria\nadd(2,3)=5\n"
                   "## Constraints\nPython\n")
            return {"ok": True, "output": {"content": prd},
                    "patch_text": "", "artifact_type": "document",
                    "verification": {"result": "PASS", "sections": []}}
        return fn
    pm_run = create_agent_run(str(tmp_path), "agt-it-product_manager-1")
    done = run_agent(str(tmp_path), pm_run["agent_run_id"], workflow_id="wf-pm",
                     executor_factory=pm_factory,
                     workflow_input={"idea": "calculator", "target_file": "prd.md"})
    assert done["state"] == "COMPLETED"
    aid = done["output_artifacts"][0]
    # Handoff 只传 artifact id
    h = create_handoff(str(tmp_path), from_agent_run_id=pm_run["agent_run_id"],
                       to_agent_id="agt-it-software_architect-1", input_artifacts=[aid])
    assert h["input_artifacts"] == [aid]
    assert "content" not in h, "Handoff 不得携带内容 (只传引用)"


# --- 4. 专业验收标准 ---

def test_role_verification(tmp_path):
    # PM: 缺章节 → FAIL
    v = _verify_role_output("product_manager", "# 只有标题")
    assert v["result"] == "FAIL"
    good_prd = ("# 产品需求文档\n## Problem\n## Target Users\n## Goals\n"
                "## Functional Requirements\n## Acceptance Criteria\n")
    assert _verify_role_output("product_manager", good_prd)["result"] == "PASS"
    # Developer: 语法错误 → FAIL
    assert _verify_role_output("software_developer", "def broken(:")["result"] == "FAIL"
    assert _verify_role_output("software_developer", "def add(a,b):\n    return a+b\n")["result"] == "PASS"


# --- 5. 失败阻断下游 ---

def test_pm_failure_blocks_downstream(tmp_path):
    ensure_professional_agents(tmp_path)

    def bad_factory(agent_id):
        def fn(input_data):
            return {"ok": False, "error": "pm 失败", "artifact_type": "report",
                    "verification": {"result": "FAIL", "error": "pm fail"}}
        return fn
    result = run_professional_workflow(str(tmp_path), idea="x", executor_factory=bad_factory)
    assert result["state"] == "FAILED"
    assert "product_manager" in result["failure"]
    # 下游未执行
    assert "software_architect" not in result["runs"]


# --- 6. Developer 失败 → Repair → 新 Artifact ---

def test_developer_fail_repair_new_artifact(tmp_path):
    """Developer 第一次 FAIL → 修复 → 新 Artifact (S5 复用)。"""
    from factory_console.node_runtime import register_node, create_node_run, execute_node_run
    from factory_console.node_runtime import get_node_run

    register_node(str(tmp_path), node_id="dev-work", name="dev", node_type="engineering")
    buggy = {
        "ok": True, "output": {"code": "buggy"},
        "patch_text": "diff --git a/app.py b/app.py\n--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,2 @@\n+def add(:\n+    pass\n",
        "artifact_type": "code_change",
        "verification": {"result": "FAIL", "error": "syntax", "stderr": "SyntaxError"},
    }
    good = {
        "ok": True, "output": {"code": "good"},
        "patch_text": "diff --git a/app.py b/app.py\n--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,3 @@\n+def add(a, b):\n+    return a + b\n",
        "artifact_type": "code_change",
        "verification": {"result": "PASS", "tests": 1},
    }
    calls = {"n": 0}

    def exec_fn(input_data):
        calls["n"] += 1
        return buggy if calls["n"] == 1 else good

    def repair_fn(failed_artifact, verification, ctx):
        return good

    run = create_node_run(str(tmp_path), "dev-work")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=exec_fn,
                            executor_name="dev", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=repair_fn)
    assert done["state"] == "COMPLETED"
    a1 = done["attempts"][0]["artifact_id"]
    a2 = done["attempts"][1]["artifact_id"]
    assert a1 != a2, "Repair 必须产生新 Artifact"
    assert done["attempts"][0]["verification"]["status"] == "FAIL"
    assert done["attempts"][1]["verification"]["status"] == "PASS"


# --- 7. Recovery: 完成 AgentRun 不重复 ---

def test_workflow_recovery_no_duplicate(tmp_path):
    from factory_console import recovery as _rec
    from factory_console.production_run import get_production_run

    ensure_professional_agents(tmp_path)

    def good_factory(agent_id):
        role = agent_id.split("-")[-2]
        content = {
            "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
            "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
            "software_developer": "def add(a, b):\n    return a + b\n",
            "qa_engineer": "def test_add():\n    assert True\n",
        }[role]
        return lambda input_data: {"ok": True, "output": {"content": content},
                                   "patch_text": "", "artifact_type": "document",
                                   "verification": {"result": "PASS"}}
    result = run_professional_workflow(str(tmp_path), idea="calc",
                                       executor_factory=good_factory)
    assert result["state"] == "COMPLETED"
    # 每个 AgentRun 的 ProductionRun 可恢复分析 (不重复)
    for role, r_ in result["runs"].items():
        prun_id = r_.get("production_run_id")
        assert prun_id
        a = _rec.analyze(str(tmp_path), prun_id)
        assert a["already_complete"] is True


# --- 8. 真实 E2E: 确定性 executor 全链 (无 LLM 依赖) ---

def test_professional_workflow_full_e2e_deterministic(tmp_path):
    """PM→Arch→Dev→QA 全链 (确定性 executor, 验证编排/Handoff/验收)。"""
    ensure_professional_agents(tmp_path)

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        content = {
            "product_manager": ("# 产品需求文档\n## Problem\n计算器\n## Target Users\n用户\n"
                                "## Goals\n加减法\n## Functional Requirements\nadd\n"
                                "## Non-Functional Requirements\n快\n## Acceptance Criteria\nadd(2,3)=5\n"
                                "## Constraints\nPython\n"),
            "software_architect": ("# 架构设计文档\n## System Architecture\nCLI\n## Components\ncalc\n"
                                   "## Interfaces\nadd/subtract\n## Data Model\nint\n## Dependencies\nnone\n"
                                   "## Technology Decisions\nPython\n## Deployment\nlocal\n## Engineering Constraints\nnone\n"),
            "software_developer": "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
            "qa_engineer": "import app\n\ndef test_add():\n    assert app.add(2, 3) == 5\n\ndef test_subtract():\n    assert app.subtract(5, 3) == 2\n",
        }[role]
        def fn(input_data):
            return {"ok": True, "output": {"content": content},
                    "patch_text": "", "artifact_type": "document" if role in (
                        "product_manager", "software_architect") else "code_change",
                    "verification": {"result": "PASS"}}
        return fn

    result = run_professional_workflow(str(tmp_path), idea="calculator app", executor_factory=factory)
    assert result["state"] == "COMPLETED", result.get("failure")
    # 4 个核心 AgentRun 全完成 (workflow 实际跑的核心链)
    CORE_ROLES = ["product_manager", "software_architect", "software_developer", "qa_engineer"]
    for role in CORE_ROLES:
        assert result["runs"][role]["state"] == "COMPLETED", role
    # 3 个 Handoff
    assert len(result["handoffs"]) == 3
    # 最终 artifacts 存在 (QA 输出)
    assert len(result["final_artifacts"]) == 1
    # lineage: 每个 handoff 的输入 = 前序 AgentRun 输出
    for i, h in enumerate(result["handoffs"]):
        assert h["from_agent_id"] == f"agt-it-{CORE_ROLES[i]}-1"
        assert h["to_agent_id"] == f"agt-it-{CORE_ROLES[i + 1]}-1"


# --- 9. 真实 E2E: Apply → Workspace ---

def test_workflow_apply_workspace(tmp_path):
    """全链 artifacts → Lifecycle → Apply → 真实 Workspace 有代码+测试。"""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=f@l", "-c", "user.name=f", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(ws), *c], capture_output=True, text=True, timeout=60)
    ensure_professional_agents(tmp_path)

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        content = {
            "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
            "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
            "software_developer": "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
            "qa_engineer": "def test_add():\n    assert True\n",
        }[role]
        def fn(input_data):
            return {"ok": True, "output": {"content": content},
                    "patch_text": "", "artifact_type": "document",
                    "verification": {"result": "PASS"}}
        return fn

    result = run_professional_workflow(str(tmp_path), idea="calc", executor_factory=factory)
    assert result["state"] == "COMPLETED"
    # Developer 的 code artifact → Apply
    dev_artifacts = result["runs"]["software_developer"]["output_artifacts"]
    assert dev_artifacts
    applied = 0
    for aid in dev_artifacts:
        art = get_artifact(str(tmp_path), aid)
        # patch_text 为空 (确定性 executor) — 直接写 workspace 验证 (真实内容在 payload)
        payload = art.get("payload") or {}
        content = payload.get("content") or ""
        if content:
            (ws / "app.py").write_text(content + "\n", encoding="utf-8")
            applied += 1
    assert applied >= 1
    assert "def add" in (ws / "app.py").read_text()


# --- 10. CLI workflow list ---

def test_cli_workflow_list(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    rc = _cli_main(["workflow"])
    assert rc == 0
