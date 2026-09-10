"""MU-CORE-02: Identity 域 (Human|Agent) + Employee/AgentEntity projection + actor 引用。

验收 (MU-CORE-02 §十):
1 创建 human/agent identity · 2 get/list/resolve · 3 persistence · 4 company isolation
5 Employee projection · 6 Agent projection · 7 Execution actor 引用 · 8 旧 id 兼容
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-org")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import node_runtime as nrt  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console.session.agent_entity import AgentEntity  # noqa: E402
from factory_console.session.agent_registry import AgentRegistry  # noqa: E402
from org import lifecycle as org_lifecycle  # noqa: E402
from org import store as org_store  # noqa: E402


def _company_with_employee(root: str) -> tuple[str, str]:
    store = org_store.OrgStore(Path(root) / "org")
    lc = org_lifecycle.OrgLifecycle(store)
    company = lc.create_company("Acme", template="software_company")
    roles = store.list_roles_by_company(company.id)
    assert roles, "software_company 模板应物化角色"
    emp = lc.hire_employee(company.id, "Alice", roles[0].id)
    return company.id, emp.id


def test_identity_create_get_list_resolve(tmp_path: Path) -> None:
    root = str(tmp_path)
    human = ident.create_identity(root, identity_type="human", company_id="C-1",
                                 display_name="Alice")
    agent = ident.create_identity(root, identity_type="agent", display_name="Agent X")
    assert human["identity_id"].startswith("I-")
    assert human["identity_type"] == "human" and human["status"] == "active"
    assert (tmp_path / "identity" / "identities.json").is_file()  # persistence
    assert ident.get_identity(root, human["identity_id"])["display_name"] == "Alice"
    assert len(ident.list_identities(root)) == 2
    assert len(ident.list_identities(root, identity_type="human")) == 1
    assert len(ident.list_identities(root, company_id="C-1")) == 1
    assert ident.resolve_identity(root, agent["identity_id"])["identity_type"] == "agent"


def test_identity_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ident.create_identity(str(tmp_path), identity_type="robot")


def test_company_isolation(tmp_path: Path) -> None:
    root = str(tmp_path)
    c1 = ident.create_identity(root, identity_type="human", company_id="C-1",
                               profile_ref="employee:E-1")
    ident.create_identity(root, identity_type="human", company_id="C-2",
                          profile_ref="employee:E-2")
    ids = [r["identity_id"] for r in ident.list_identities(root, company_id="C-1")]
    assert ids == [c1["identity_id"]]
    # 同一 profile_ref 跨公司投影必须拒绝
    with pytest.raises(ValueError):
        ident.ensure_identity(root, identity_type="human",
                              profile_ref="employee:E-1", company_id="C-2")


def test_employee_projection(tmp_path: Path) -> None:
    root = str(tmp_path)
    cid, eid = _company_with_employee(root)
    human = ident.project_employee(root, eid)
    assert human["identity_type"] == "human"
    assert human["company_id"] == cid               # Human -> 公司边界
    assert human["profile_ref"] == f"employee:{eid}"
    assert ident.project_employee(root, eid)["identity_id"] == human["identity_id"]  # 幂等
    assert ident.resolve_actor_identity(root, eid) == human["identity_id"]           # 旧 id 兼容


def test_agent_projection(tmp_path: Path) -> None:
    root = str(tmp_path)
    agents_file = tmp_path / "agents.json"
    AgentRegistry(agents_file=agents_file).add(
        AgentEntity(id="agt-it-pm-1", role="pm", industry="it"))
    agent = ident.project_agent(root, "agt-it-pm-1", agents_file=agents_file)
    assert agent["identity_type"] == "agent"
    assert agent["profile_ref"] == "agent:agt-it-pm-1"
    assert agent["company_id"] == ""                # Agent 当前无公司绑定 (可跨公司)
    assert ident.resolve_actor_identity(root, "agt-it-pm-1") == agent["identity_id"]


def test_actor_reference_in_execution(tmp_path: Path) -> None:
    root = str(tmp_path)
    agents_file = tmp_path / "agents.json"
    AgentRegistry(agents_file=agents_file).add(
        AgentEntity(id="agt-it-pm-1", role="pm", industry="it"))
    agent = ident.project_agent(root, "agt-it-pm-1", agents_file=agents_file)

    nrt.register_node(root, node_id="n1", name="N1", node_type="task")
    run = nrt.create_node_run(root, "n1")
    nrt.transition_node_run(root, run["run_id"], "RUNNING", actor="agt-it-pm-1")
    recorded = nrt.get_node_run(root, run["run_id"])
    assert recorded["history"][-1]["actor"] == "agt-it-pm-1"
    assert recorded["history"][-1]["actor_identity_id"] == agent["identity_id"]

    # 未登记 actor -> 空引用, 不阻断执行
    nrt.transition_node_run(root, run["run_id"], "VERIFYING", actor="system")
    recorded = nrt.get_node_run(root, run["run_id"])
    assert recorded["history"][-1]["actor_identity_id"] == ""
