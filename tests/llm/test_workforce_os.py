"""S30: Workforce Intelligence & Organization Foundation。

覆盖:
- Organization → Department → Workforce 层级 + lineage
- Workforce Lifecycle (DRAFT→ACTIVE→SUSPENDED→RETIRED; 非法迁移拒绝; append-only)
- AgentProfile (role/capabilities/skills/tools/model/policies 确定性 binding)
- Capability Contract (确定性, 非 prompt)
- 确定性 Agent Selection (capability match → permission; 非 LLM)
- Performance Profile (从 Production Evidence 投影; 无证据 → sample_count 0)
- Governance (非 DRAFT 不可 attach; agent 不能自改权限)
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.workforce_os import (  # noqa: E402
    create_organization, create_department, create_workforce, workforce_status,
    attach_agent, get_workforce, list_agent_profiles, capabilities_list,
    select_agent_deterministic, agent_performance, workforce_os_lineage,
)


# --- Organization → Department → Workforce 层级 ---

def test_org_hierarchy(tmp_path):
    org = create_organization(str(tmp_path), name="AI Factory")
    dept = create_department(str(tmp_path), org_id=org["org_id"], name="Engineering")
    wf = create_workforce(str(tmp_path), dept_id=dept["dept_id"], name="production")
    assert wf["dept_id"] == dept["dept_id"]
    assert wf["status"] == "DRAFT"
    # org 引用 dept
    orgs = create_organization  # noqa: F841
    from factory_console.workforce_os import list_organizations
    org_after = list_organizations(str(tmp_path))[0]
    assert dept["dept_id"] in org_after["departments"]


# --- Lifecycle ---

def test_lifecycle(tmp_path):
    wf = create_workforce(str(tmp_path))
    workforce_status(str(tmp_path), wf["workforce_id"], target="ACTIVE")
    assert get_workforce(str(tmp_path), wf["workforce_id"])["status"] == "ACTIVE"
    workforce_status(str(tmp_path), wf["workforce_id"], target="SUSPENDED")
    assert get_workforce(str(tmp_path), wf["workforce_id"])["status"] == "SUSPENDED"
    # 非法迁移: SUSPENDED → DRAFT 拒绝
    with pytest.raises(ValueError, match="非法状态迁移"):
        workforce_status(str(tmp_path), wf["workforce_id"], target="DRAFT")
    # RETIRED 终态
    workforce_status(str(tmp_path), wf["workforce_id"], target="RETIRED")
    assert get_workforce(str(tmp_path), wf["workforce_id"])["status"] == "RETIRED"
    # append-only history
    wf_after = get_workforce(str(tmp_path), wf["workforce_id"])
    assert len(wf_after["history"]) >= 4


# --- Attach + Governance ---

def test_attach_requires_draft(tmp_path):
    wf = create_workforce(str(tmp_path))
    workforce_status(str(tmp_path), wf["workforce_id"], target="ACTIVE")
    # 非 DRAFT 不可 attach
    with pytest.raises(ValueError, match="非 DRAFT"):
        attach_agent(str(tmp_path), workforce_id=wf["workforce_id"], role="software_developer")
    # DRAFT 可 attach
    wf2 = create_workforce(str(tmp_path), name="draft-wf")
    p = attach_agent(str(tmp_path), workforce_id=wf2["workforce_id"], role="software_developer")
    assert p["role"] == "software_developer"
    assert "implement" in p["capabilities"]
    assert p["tools"]  # skill/tool/model binding
    assert p["model"] == "default"


# --- AgentProfile Contract ---

def test_agent_profile_binding(tmp_path):
    wf = create_workforce(str(tmp_path))
    attach_agent(str(tmp_path), workforce_id=wf["workforce_id"], role="qa_engineer")
    profs = list_agent_profiles(str(tmp_path))
    qa = next(p for p in profs if p["role"] == "qa_engineer")
    assert qa["capabilities"] == ["verify", "test", "quality_decision"]
    assert qa["policies"]  # policy binding
    assert qa["agent_id"]


# --- Capability Contract ---

def test_capability_contract(tmp_path):
    caps = capabilities_list(str(tmp_path))
    assert len(caps) >= 10  # 7 角色多能力
    implement = next(c for c in caps if c["capability"] == "implement")
    assert implement["role"] == "software_developer"
    assert implement["permitted"] == "implement_code"


# --- 确定性 Selection ---

def test_deterministic_selection(tmp_path):
    sel = select_agent_deterministic(str(tmp_path), required_capability="implement")
    assert sel["selected"] is True
    assert sel["role"] == "software_developer"
    assert "capability match" in sel["reason"]  # 确定性, 非 LLM
    sel2 = select_agent_deterministic(str(tmp_path), required_capability="nonexistent_cap")
    assert sel2["selected"] is False


# --- Performance (从 Evidence 投影, 无数据诚实) ---

def test_performance_projection(tmp_path):
    perf = agent_performance(str(tmp_path), "agt-nonexistent")
    assert perf["sample_count"] == 0
    assert "无 Production Evidence" in perf["explain"]  # 不造数据


# --- Lineage ---

def test_lineage(tmp_path):
    org = create_organization(str(tmp_path))
    dept = create_department(str(tmp_path), org_id=org["org_id"], name="Eng")
    wf = create_workforce(str(tmp_path), dept_id=dept["dept_id"])
    attach_agent(str(tmp_path), workforce_id=wf["workforce_id"], role="software_developer")
    lg = workforce_os_lineage(str(tmp_path))
    assert len(lg["organizations"]) == 1
    assert len(lg["workforces"]) == 1
    assert len(lg["workforces"][0]["agents"]) == 1


# --- CLI ---

def test_cli_workforce_os(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["org", "create", "TestOrg", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["org", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["workforce-os", "create", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["workforce-os", "capabilities", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["workforce-os", "select", "--capability", "implement", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["workforce-os", "perf", "agt-x", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["workforce-os", "status", "wf-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_workforce_os(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/organizations", json={"name": "AI Factory"})
    assert resp.status_code == 200
    org = resp.json()
    assert org["org_id"].startswith("org-")
    resp = client.get("/api/organizations")
    assert resp.status_code == 200
    resp = client.post("/api/workforces", json={"name": "production"})
    assert resp.status_code == 200
    wf = resp.json()
    assert wf["status"] == "DRAFT"
    resp = client.get(f"/api/workforces/{wf['workforce_id']}")
    assert resp.status_code == 200
    resp = client.post(f"/api/workforces/{wf['workforce_id']}/attach",
                       json={"role": "software_developer"})
    assert resp.status_code == 200
    resp = client.post(f"/api/workforces/{wf['workforce_id']}/status", json={"status": "ACTIVE"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"
    resp = client.get("/api/agent-profiles")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    resp = client.post("/api/workforces/select", json={"capability": "implement"})
    assert resp.status_code == 200
    assert resp.json()["selected"] is True
    resp = client.get("/api/workforce-os/lineage")
    assert resp.status_code == 200
