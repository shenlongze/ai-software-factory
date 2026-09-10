"""MU-CORE-04: Workforce OS Core（SSOT + boundary + 兼容适配器）。

验收:
1 Workforce CRUD/lifecycle · 2 Identity 集成 · 3 Role/Professional 集成 · 4 persistence/reload
5 company isolation · 6 compat(workforce_os) · 7 真实 runtime path · 8 无第二 truth / Capability 契约
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-org"),
           str(_ROOT / "factory-exec")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import os_core_company_organization as osco  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console import os_core_professional as prof  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402
from factory_console import workforce_os as wfos  # noqa: E402


def _setup(root: str) -> dict:
    company = osco.create_company(root, name="Acme")
    dept = osco.create_department(root, company_id=company["id"], name="Engineering")
    human = ident.create_identity(root, identity_type="human",
                                  company_id=company["id"], display_name="Alice")
    dom = prof.create_professional_domain(root, name="Software Engineering")
    prole = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                          name="Backend Engineer", role_ref="developer",
                                          capability_refs=["implement_code"])
    return {"company": company, "dept": dept, "human": human,
            "domain": dom, "prole": prole}


# ---------------------------------------------------------------- 1 CRUD / lifecycle

def test_workforce_crud_and_lifecycle(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _setup(root)
    rec = wf.create_workforce(root, name="Eng WF", company_id=ctx["company"]["id"],
                              scope_type="department", scope_id=ctx["dept"]["id"],
                              capability_refs=["implement_code"])
    assert rec["workforce_id"].startswith("WF-") and rec["status"] == "draft"
    assert rec["capability_refs"] == ["implement_code"]        # contract only
    assert wf.get_workforce(root, rec["workforce_id"])["name"] == "Eng WF"
    assert len(wf.list_workforces(root)) == 1

    wf.set_workforce_status(root, rec["workforce_id"], "active")
    assert wf.get_workforce(root, rec["workforce_id"])["status"] == "active"
    with pytest.raises(ValueError):
        wf.set_workforce_status(root, rec["workforce_id"], "draft")   # active -> draft 非法
    wf.set_workforce_status(root, rec["workforce_id"], "retired")
    assert wf.get_workforce(root, rec["workforce_id"])["status"] == "retired"
    wf.update_workforce(root, rec["workforce_id"], description="retired team")
    assert wf.get_workforce(root, rec["workforce_id"])["description"] == "retired team"


# ---------------------------------------------------------------- 2 Identity 集成

def test_identity_membership(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _setup(root)
    rec = wf.create_workforce(root, name="Eng WF", company_id=ctx["company"]["id"],
                              scope_type="global")
    wf.add_member(root, rec["workforce_id"], ctx["human"]["identity_id"],
                  professional_role_ref=ctx["prole"]["professional_role_id"])
    got = wf.get_workforce(root, rec["workforce_id"])
    assert ctx["human"]["identity_id"] in got["member_refs"]
    assert ctx["prole"]["professional_role_id"] in got["professional_role_refs"]
    resolved = wf.resolve_workforce(root, rec["workforce_id"])
    assert resolved["members"][0]["identity_id"] == ctx["human"]["identity_id"]
    assert resolved["professional_roles"][0]["professional_role_id"] == ctx["prole"]["professional_role_id"]
    # 未知 Identity / 未知 ProfessionalRole 必须拒绝
    with pytest.raises(ValueError):
        wf.add_member(root, rec["workforce_id"], "I-nope")
    with pytest.raises(ValueError):
        wf.assign_professional_role(root, rec["workforce_id"], "PR-nope")
    # remove
    wf.remove_member(root, rec["workforce_id"], ctx["human"]["identity_id"])
    assert wf.get_workforce(root, rec["workforce_id"])["member_refs"] == []


# ---------------------------------------------------------------- 4 persistence / reload

def test_persistence_reload(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _setup(root)
    rec = wf.create_workforce(root, name="Persist WF", company_id=ctx["company"]["id"])
    wf.add_member(root, rec["workforce_id"], ctx["human"]["identity_id"])
    assert (tmp_path / "workforce" / "workforces.json").is_file()
    # 模拟 reload: 直接重新读取 SSOT
    reloaded = wf.get_workforce(root, rec["workforce_id"])
    assert reloaded["member_refs"] == [ctx["human"]["identity_id"]]


# ---------------------------------------------------------------- 5 company isolation

def test_company_scope_validation(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _setup(root)
    other = osco.create_company(root, name="Other Co")
    with pytest.raises(ValueError):     # 不存在的 company
        wf.create_workforce(root, name="X", company_id="C-nope")
    with pytest.raises(ValueError):     # department 与 company 不匹配
        wf.create_workforce(root, name="X", company_id=other["id"],
                            scope_type="department", scope_id=ctx["dept"]["id"])
    with pytest.raises(ValueError):     # department scope 必须提供 scope_id
        wf.create_workforce(root, name="X", scope_type="department")
    with pytest.raises(ValueError):     # global scope 不接受 scope_id
        wf.create_workforce(root, name="X", scope_type="global", scope_id=ctx["dept"]["id"])
    # company 过滤
    wf.create_workforce(root, name="A", company_id=ctx["company"]["id"])
    wf.create_workforce(root, name="B", company_id=other["id"])
    assert len(wf.list_workforces(root, company_id=ctx["company"]["id"])) == 1


# ---------------------------------------------------------------- 6 compat(workforce_os)

def test_workforce_os_compat_adapter(tmp_path: Path) -> None:
    root = str(tmp_path)
    compat = wfos.create_workforce(root, name="production")
    assert compat["status"] == "DRAFT" and compat["workforce_id"].startswith("WF-")
    # 旧 workforce store 不再写入 (无第二 truth)
    assert not (tmp_path / "ops" / "workforce_os" / "workforces.json").exists()
    wfos.workforce_status(root, compat["workforce_id"], target="ACTIVE")
    assert wfos.get_workforce(root, compat["workforce_id"])["status"] == "ACTIVE"
    # attach: AgentProfile 落 profile store; 成员引用 Agent Identity
    wf2 = wfos.create_workforce(root, name="draft-wf")
    profile = wfos.attach_agent(root, workforce_id=wf2["workforce_id"],
                                role="software_developer")
    assert profile["role"] == "software_developer"
    got = wfos.get_workforce(root, wf2["workforce_id"])
    assert got["member_refs"]                              # 引用 Identity
    assert ident.get_identity(root, got["member_refs"][0])["identity_type"] == "agent"
    assert got["agents"][0]["agent_id"] == profile["agent_id"]   # profile 投影
    # lineage 仍可用
    assert len(wfos.workforce_os_lineage(root)["workforces"]) == 2


# ---------------------------------------------------------------- 7 真实 runtime path

def test_runtime_chain_company_identity_professional_workforce(tmp_path: Path) -> None:
    root = str(tmp_path)
    company = osco.create_company(root, name="Acme")
    dept = osco.create_department(root, company_id=company["id"], name="Data")
    human = ident.create_identity(root, identity_type="human",
                                  company_id=company["id"], display_name="Data Lead")
    dom = prof.create_professional_domain(root, name="Data")
    prole = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                          name="Data Engineer", capability_refs=["etl"])
    rec = wf.create_workforce(root, name="Data WF", company_id=company["id"],
                              scope_type="department", scope_id=dept["id"],
                              professional_role_refs=[prole["professional_role_id"]],
                              capability_refs=["etl"])
    wf.add_member(root, rec["workforce_id"], human["identity_id"])
    resolved = wf.resolve_workforce(root, rec["workforce_id"])
    assert resolved["workforce"]["company_id"] == company["id"]
    assert resolved["members"][0]["display_name"] == "Data Lead"
    assert resolved["professional_roles"][0]["name"] == "Data Engineer"


# ---------------------------------------------------------------- 8 无第二 truth / Capability 契约

def test_no_second_truth_and_capability_contract(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _setup(root)
    wf.create_workforce(root, name="W", company_id=ctx["company"]["id"],
                        capability_refs=["implement_code"])
    assert not (tmp_path / "ops" / "workforce_os" / "workforces.json").exists()
    assert not (tmp_path / "capability").exists()          # 不实现 Capability
    assert not (tmp_path / "workforce" / "roles.json").exists()  # 不建第二套 Role
