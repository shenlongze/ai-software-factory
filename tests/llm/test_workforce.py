"""S16: Multi-Agent Professional Workforce。

覆盖:
- Role Capability Contract (能力声明, 非 prompt)
- Permission Boundary (enforce, 跨角色拒绝, forbidden)
- Agent selection (Registry → AgentEntity)
- TaskRecord
- Workforce Lineage (全链)
- Multi-Agent E2E (PM→Arch→Dev→QA 独立 Loop)
- Failure/Repair E2E (QA FAIL → Repair → PASS)
- CLI/API
- 扩展角色 (market/ux/release)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.workforce import (  # noqa: E402
    ROLE_CAPABILITIES, PERMISSION_MATRIX, FORBIDDEN_ACTIONS,
    enforce_permission, capabilities, select_agent, list_agents,
    create_task, get_tasks, workforce_lineage, run_workforce,
    WORKFORCE_WORKFLOWS,
)
from factory_console.professional_workflow import (  # noqa: E402
    ensure_professional_agents, BUILTIN_CALC_TESTS, verify_code_with_pytest,
)


# --- Role Capability Contract ---

def test_role_capabilities(tmp_path):
    assert "product_manager" in ROLE_CAPABILITIES
    assert "create_prd" in ROLE_CAPABILITIES["product_manager"]
    assert "software_developer" in ROLE_CAPABILITIES
    assert "implement" in ROLE_CAPABILITIES["software_developer"]
    assert "qa_engineer" in ROLE_CAPABILITIES
    assert "verify" in ROLE_CAPABILITIES["qa_engineer"]
    # 扩展角色
    assert "market_analyst" in ROLE_CAPABILITIES
    assert "ux_designer" in ROLE_CAPABILITIES
    assert "release_engineer" in ROLE_CAPABILITIES
    assert capabilities("product_manager") == ["discover_product", "create_prd", "product_decision"]


# --- Permission Boundary ---

def test_permission_boundary(tmp_path):
    # 允许: PM 建 PRD
    enforce_permission("product_manager", "create_prd")
    # 拒绝: PM 改代码
    with pytest.raises(PermissionError):
        enforce_permission("product_manager", "implement_code")
    # 拒绝: Developer 发布
    with pytest.raises(PermissionError):
        enforce_permission("software_developer", "release")
    # 拒绝: Developer override QA
    with pytest.raises(PermissionError):
        enforce_permission("software_developer", "override_qa")
    # QA 可验证
    enforce_permission("qa_engineer", "verify_code")
    # 未知 action (未注册) → 不拒绝 (默认开放, 但核心 action 都注册)
    enforce_permission("product_manager", "unknown_action")


# --- Agent selection ---

def test_agent_selection(tmp_path):
    ensure_professional_agents(tmp_path)
    pm = select_agent(str(tmp_path), "product_manager")
    assert pm is not None
    assert pm["role"] == "product_manager"
    dev = select_agent(str(tmp_path), "software_developer")
    assert dev is not None
    agents = list_agents(str(tmp_path))
    roles = {a["role"] for a in agents}
    assert "product_manager" in roles and "qa_engineer" in roles
    # 扩展角色已预置
    assert "market_analyst" in roles and "release_engineer" in roles
    # 每个 agent 有 capabilities
    for a in agents:
        assert "capabilities" in a


# --- TaskRecord ---

def test_task_record(tmp_path):
    t = create_task(str(tmp_path), role="software_developer",
                    objective="implement calculator", production_run_id="prun-x")
    assert t["task_id"].startswith("task-")
    assert t["status"] == "PENDING"
    tasks = get_tasks(str(tmp_path), production_run_id="prun-x")
    assert len(tasks) == 1
    assert tasks[0]["role"] == "software_developer"


# --- Workforce Lineage ---

def test_workforce_lineage_structure(tmp_path):
    ensure_professional_agents(tmp_path)
    # 空 run → 结构存在
    lg = workforce_lineage(str(tmp_path), "prun-none")
    assert "nodes" in lg and "experiences" in lg and "decisions" in lg
    assert "tasks" in lg and "artifacts" in lg


# --- Multi-Agent E2E (确定性: PM→Arch→Dev→QA 独立 Loop) ---

def _make_factory():
    content = {
        "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
        "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
        "software_developer": ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                               "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                               "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n"),
        "qa_engineer": "def test_add():\n    assert True\n",
        "market_analyst": "# 市场分析\n## Market\n## Competitors\n",
        "ux_designer": "# UX 设计\n## User Flow\n## Screens\n",
        "release_engineer": "# 发布说明\n## Version\n## Checklist\n",
    }
    calls = {}

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        def fn(input_data):
            calls[role] = calls.get(role, 0) + 1
            c = content.get(role, f"# {role}\n## Section\n")
            if role == "software_developer":
                ver = verify_code_with_pytest(c, BUILTIN_CALC_TESTS)
            else:
                ver = {"result": "PASS"}
            if ver.get("status") == "FAIL" or ver.get("result") == "FAIL":
                return {"ok": False, "error": "verify fail", "artifact_type": "report",
                        "verification": {"result": "FAIL"}}
            return {"ok": True, "output": {"content": c}, "patch_text": "",
                    "artifact_type": "document", "verification": {"result": "PASS"}}
        return fn
    return factory, calls


def test_multi_agent_e2e(tmp_path):
    """PM→Arch→Dev→QA 独立 AgentRun, 全 COMPLETED, Handoff 串联。"""
    ensure_professional_agents(tmp_path)
    factory, calls = _make_factory()
    result = run_workforce(str(tmp_path), idea="calculator",
                           executor_factory=factory,
                           experience_guidance=False)
    assert result["state"] == "COMPLETED", result.get("failure")
    # 4 角色独立执行
    assert calls.get("product_manager") == 1
    assert calls.get("software_architect") == 1
    assert calls.get("software_developer") == 1
    assert calls.get("qa_engineer") == 1
    # 每角色独立 AgentRun (非 central mega-agent)
    for role in ("product_manager", "software_architect", "software_developer", "qa_engineer"):
        r = result["runs"][role]
        assert r["state"] == "COMPLETED"
        assert r.get("production_run_id"), f"{role} 必须有独立 ProductionRun"
    # TaskRecords 已创建
    assert len(get_tasks(str(tmp_path))) >= 4


# --- Failure/Repair E2E (QA FAIL → Repair → PASS) ---

def test_failure_repair_e2e(tmp_path):
    """Developer 失败 → Repair → PASS (复用 S12)。"""
    ensure_professional_agents(tmp_path)
    bad_code = ("def add(a, b):\n    return a - b\n\ndef subtract(a, b):\n    return a + b\n\n"
                "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    return a / b\n")
    good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                 "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                 "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        def fn(input_data):
            c = {
                "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
                "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
                "software_developer": bad_code,
                "qa_engineer": "def test_add():\n    assert True\n",
            }[role]
            if role == "software_developer":
                ver = verify_code_with_pytest(c, BUILTIN_CALC_TESTS)
                # verification FAIL (ok=True) → 触发 repair_fn (S12 语义)
                return {"ok": True, "output": {"content": c}, "patch_text": "",
                        "artifact_type": "code_change", "verification": ver, "content": c}
            return {"ok": True, "output": {"content": c}, "patch_text": "",
                    "artifact_type": "document", "verification": {"result": "PASS"}}
        return fn

    def dev_repair(failed_artifact, verification, ctx):
        ver = verify_code_with_pytest(good_code, BUILTIN_CALC_TESTS)
        return {"ok": ver["status"] == "PASS", "output": {"content": good_code},
                "patch_text": "", "artifact_type": "code_change", "verification": ver,
                "content": good_code}

    import factory_console.professional_workflow as _pw
    _orig = _pw.build_developer_repair_fn
    _pw.build_developer_repair_fn = lambda root, idea, arch: dev_repair
    try:
        result = run_workforce(str(tmp_path), idea="calculator",
                               executor_factory=factory,
                               max_repair=1, experience_guidance=False)
    finally:
        _pw.build_developer_repair_fn = _orig
    assert result["state"] == "COMPLETED", result.get("failure")
    # 真实 repair: Developer attempts FAIL→PASS
    dev = result["runs"]["software_developer"]
    assert dev["state"] == "COMPLETED"


# --- CLI ---

def test_cli_workforce(tmp_path):
    ensure_professional_agents(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["workforce", "list"]) == 0
    assert _cli_main(["workforce", "agents", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["workforce", "runs", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_workforce(tmp_path):
    ensure_professional_agents(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get("/api/workforce")
    assert resp.status_code == 200
    assert len(resp.json()["workflows"]) >= 2
    resp = client.get("/api/workforce/agents")
    assert resp.status_code == 200
    roles = {a["role"] for a in resp.json()["items"]}
    assert "product_manager" in roles and "release_engineer" in roles
    resp = client.get("/api/workforce/runs")
    assert resp.status_code == 200
