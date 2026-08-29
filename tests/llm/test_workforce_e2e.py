"""S11: Workforce E2E Production Run — 真实 pytest QA + 真实失败/修复。

覆盖:
1. QA → verify_pytest (真实 subprocess)
2. pytest failure propagation (FAIL → 不 COMPLETED)
3. Repair creates new Artifact
4. Repair → pytest PASS
5. Full lineage
6. Apply → Workspace
7. 真实 LLM/codex 路径 (环境可用时)

Automated deterministic E2E (稳定) + Real external E2E (标记 GAP 环境依赖)
分开报告。
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
    verify_code_with_pytest, ensure_professional_agents, run_professional_workflow,
    build_real_executor_factory, run_real_workforce_e2e, PROFESSIONAL_ROLES,
)


# --- 1. QA → 真实 verify_pytest ---

def test_qa_real_pytest_pass(tmp_path):
    """真实 pytest: 好代码 + 好测试 → PASS。"""
    code = "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n"
    test = ("import app\n\ndef test_add():\n    assert app.add(2, 3) == 5\n\n"
            "def test_subtract():\n    assert app.subtract(5, 3) == 2\n")
    r = verify_code_with_pytest(code, test)
    assert r["status"] == "PASS", r.get("stderr")
    assert r["exit_code"] == 0
    assert "command" in r and "duration_s" in r


def test_qa_real_pytest_fail(tmp_path):
    """真实 pytest: 坏代码 → FAIL (exit_code != 0)。"""
    code = "def add(a, b):\n    return a - b\n"  # 故意错 (减号)
    test = "import app\n\ndef test_add():\n    assert app.add(2, 3) == 5\n"
    r = verify_code_with_pytest(code, test)
    assert r["status"] == "FAIL"
    assert r["exit_code"] != 0


# --- 2. pytest failure propagation (经 Agent) ---

def test_pytest_fail_propagates(tmp_path):
    """QA 的 pytest FAIL → 整个 AgentRun FAILED (不伪装 COMPLETED)。"""
    ensure_professional_agents(tmp_path)

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        def fn(input_data):
            if role == "product_manager":
                c = "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n"
                return {"ok": True, "output": {"content": c}, "patch_text": "",
                        "artifact_type": "document", "verification": {"result": "PASS"}}
            if role == "software_architect":
                c = "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n"
                return {"ok": True, "output": {"content": c}, "patch_text": "",
                        "artifact_type": "document", "verification": {"result": "PASS"}}
            if role == "software_developer":
                c = "def add(a, b):\n    return a - b\n"  # 故意错
                return {"ok": True, "output": {"content": c}, "patch_text": "",
                        "artifact_type": "code_change", "verification": {"result": "PASS"}}
            if role == "qa_engineer":
                # QA 生成测试 (固定) → 真实 pytest → 失败
                test = "import app\n\ndef test_add():\n    assert app.add(2, 3) == 5\n"
                code = str(next(iter((input_data.get("context") or {}).values()), ""))
                r = verify_code_with_pytest(code, test)
                return {"ok": r["status"] == "PASS", "output": {"content": test, "pytest": r},
                        "patch_text": "", "error": r.get("stderr", ""),
                        "artifact_type": "test", "verification": r}
            return {"ok": False, "error": "?", "artifact_type": "report",
                    "verification": {"result": "FAIL"}}
        return fn

    result = run_professional_workflow(str(tmp_path), idea="calc", executor_factory=factory)
    assert result["state"] == "FAILED"
    assert "qa_engineer" in result["failure"]
    assert result["runs"]["qa_engineer"]["state"] == "FAILED"


# --- 3/4. Repair 产生新 Artifact + pytest PASS ---

def test_repair_new_artifact_pytest_pass(tmp_path):
    """Developer 坏代码 → QA pytest FAIL → 修复 → 新代码 → pytest PASS (A≠B)。"""
    from factory_console.node_runtime import register_node, create_node_run, execute_node_run

    register_node(str(tmp_path), node_id="dev", name="dev", node_type="engineering")
    bad_code = "def add(a, b):\n    return a - b\n"
    good_code = "def add(a, b):\n    return a + b\n"
    test = "import app\n\ndef test_add():\n    assert app.add(2, 3) == 5\n"

    def exec_fn(input_data):
        code = input_data.get("_code", bad_code)
        ver = verify_code_with_pytest(code, test)
        return {"ok": True, "output": {"content": code}, "patch_text": "",
                "artifact_type": "code_change", "verification": ver, "content": code}

    def repair_fn(failed_artifact, verification, ctx):
        return exec_fn({**_ctx_copy(ctx), "_code": good_code})

    def _ctx_copy(ctx):
        return dict(ctx)

    run = create_node_run(str(tmp_path), "dev")
    done = execute_node_run(str(tmp_path), run["run_id"], executor_fn=exec_fn,
                            executor_name="dev", artifact_root=str(tmp_path),
                            max_attempts=2, repair_fn=repair_fn)
    assert done["state"] == "COMPLETED"
    a1 = done["attempts"][0]["artifact_id"]
    a2 = done["attempts"][1]["artifact_id"]
    assert a1 != a2, "Repair 必须产生新 Artifact"
    assert done["attempts"][0]["verification"]["status"] == "FAIL"
    assert done["attempts"][1]["verification"]["status"] == "PASS"


# --- 5. Full lineage ---

def test_full_lineage(tmp_path):
    """PRD → Arch → Code → Test 全链 lineage 可追溯。"""
    ensure_professional_agents(tmp_path)

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        content = {
            "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
            "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
            "software_developer": "def add(a, b):\n    return a + b\n",
            "qa_engineer": "def test_add():\n    assert True\n",
        }[role]
        def fn(input_data):
            return {"ok": True, "output": {"content": content}, "patch_text": "",
                    "artifact_type": "document", "verification": {"result": "PASS"}}
        return fn

    result = run_professional_workflow(str(tmp_path), idea="calc", executor_factory=factory)
    assert result["state"] == "COMPLETED"
    # 每步 Handoff lineage
    h = result["handoffs"]
    assert len(h) == 3
    assert h[0]["from_agent_id"] == "agt-it-product_manager-1"
    assert h[0]["to_agent_id"] == "agt-it-software_architect-1"
    assert h[2]["to_agent_id"] == "agt-it-qa_engineer-1"


# --- 6. Apply → Workspace (真实文件) ---

def test_apply_to_workspace_real(tmp_path):
    """最终代码 Apply → 真实 Workspace 文件。"""
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
            return {"ok": True, "output": {"content": content}, "patch_text": "",
                    "artifact_type": "document", "verification": {"result": "PASS"}}
        return fn

    result = run_professional_workflow(str(tmp_path), idea="calc", executor_factory=factory)
    assert result["state"] == "COMPLETED"
    dev_artifacts = result["runs"]["software_developer"]["output_artifacts"]
    # 从 artifact payload 写 workspace (真实内容)
    from factory_console.artifact_lifecycle import get_artifact
    for aid in dev_artifacts:
        art = get_artifact(str(tmp_path), aid)
        payload = art.get("payload") or {}
        content = payload.get("content") or ""
        if content:
            (ws / "app.py").write_text(content + "\n", encoding="utf-8")
    assert (ws / "app.py").exists()
    assert "def add" in (ws / "app.py").read_text()


# --- 7. Real external E2E (环境可用时跑, 否则 GAP) ---

def test_real_external_e2e_available(tmp_path):
    """真实 LLM/codex 环境检查 (不跑全链, 只验证依赖可用性)。"""
    import shutil
    from factory_console.workflow_runner import has_llm_key
    if shutil.which("codex") is None:
        pytest.skip("codex CLI 不可用 (ENVIRONMENT BLOCKED)")
    if not has_llm_key():
        pytest.skip("LLM key 缺失 (测试进程未 source .env — 真实环境需 factory 启动时注入)")
