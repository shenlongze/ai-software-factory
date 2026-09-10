"""MU-CORE-03: Role Definition / Role Assignment / Professional Domain·Role。

验收 (MU-CORE-03 §十):
1-2 Role Definition (SSOT=exec/roles.py, 无第二份) · 3-4 Assignment 持久化+解析
5-6 Human/Agent Identity 承担 Role · 7-9 Professional Domain/Role 持久化与链接
10 无第二套 Role truth · 11 Company isolation · 12 Identity 兼容
13-14 原有消费者回归(见独立测试批次) · 15 ruff (命令级)
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
from factory_console import os_core_role as role  # noqa: E402
from factory_console import os_core_capability as cap  # noqa: E402

def _caps(root: str, *names: str) -> list[str]:
    """MU-CORE-07: capability_refs 必须指向 Capability SSOT (按 name 幂等)。"""

    out = []
    for n in names:
        existing = next((c for c in cap.list_capabilities(root) if c["name"] == n), None)
        out.append((existing or cap.create_capability(root, name=n))["capability_id"])
    return out



def _company_and_identities(root: str) -> tuple[str, str, str]:
    company = osco.create_company(root, name="Acme")
    human = ident.create_identity(root, identity_type="human",
                                  company_id=company["id"], display_name="Alice")
    agent = ident.create_identity(root, identity_type="agent", display_name="Agent X")
    return company["id"], human["identity_id"], agent["identity_id"]


# ---------------------------------------------------------------- 1-2 Role Definition

def test_role_definition_ssot() -> None:
    defs = role.list_role_definitions()
    assert defs and all(d["source"] == "exec/roles.py" for d in defs)
    dev = role.get_role_definition("developer")
    assert dev is not None and dev["role_id"] == "developer"
    # 别名解析走同一注册表 (pm -> product-manager)
    assert role.resolve_role_definition("pm")["role_id"] == "product-manager"
    with pytest.raises(ValueError):
        role.resolve_role_definition("no-such-role")


def test_no_second_role_definition_store(tmp_path: Path) -> None:
    root = str(tmp_path)
    cid, hid, _ = _company_and_identities(root)
    role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                scope_type="company", scope_id=cid)
    # Role Definition 不落第二份 store (SSOT = exec/roles.py 代码注册表)
    assert not (tmp_path / "role" / "definitions.json").exists()


# ---------------------------------------------------------------- 3-6 Assignment

def test_role_assignment_create_and_persist(tmp_path: Path) -> None:
    root = str(tmp_path)
    cid, hid, aid = _company_and_identities(root)
    a = role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                    scope_type="company", scope_id=cid)
    assert a["assignment_id"].startswith("RA-") and a["status"] == "active"
    assert (tmp_path / "role" / "assignments.json").is_file()          # persistence
    assert role.get_role_assignment(root, a["assignment_id"])["role_id"] == "developer"


def test_identity_assignment_definition_resolution(tmp_path: Path) -> None:
    root = str(tmp_path)
    cid, hid, aid = _company_and_identities(root)
    role.create_role_assignment(root, identity_id=hid, role_id="pm",
                                scope_type="company", scope_id=cid)
    role.create_role_assignment(root, identity_id=aid, role_id="tester",
                                scope_type="global")
    human_roles = role.resolve_identity_roles(root, hid)
    agent_roles = role.resolve_identity_roles(root, aid)
    assert human_roles[0]["role"]["role_id"] == "product-manager"       # 别名->canonical
    assert human_roles[0]["assignment"]["scope_type"] == "company"
    assert agent_roles[0]["role"]["role_id"] == "tester"
    assert agent_roles[0]["assignment"]["scope_type"] == "global"


def test_duplicate_assignment_rejected(tmp_path: Path) -> None:
    root = str(tmp_path)
    cid, hid, _ = _company_and_identities(root)
    role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                scope_type="company", scope_id=cid)
    with pytest.raises(ValueError):
        role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                    scope_type="company", scope_id=cid)


# ---------------------------------------------------------------- 7-9 Professional

def test_professional_domain_and_role(tmp_path: Path) -> None:
    root = str(tmp_path)
    dom = prof.create_professional_domain(root, name="Software Engineering")
    assert (tmp_path / "professional" / "domains.json").is_file()
    assert prof.get_professional_domain(root, dom["domain_id"])["name"] == "Software Engineering"

    pr = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                       name="Backend Engineer", role_ref="developer",
                                       capability_refs=_caps(root, "implement_code"))
    assert (tmp_path / "professional" / "roles.json").is_file()
    stored = prof.get_professional_role(root, pr["professional_role_id"])
    assert stored["professional_domain_id"] == dom["domain_id"]          # -> Domain
    assert stored["role_ref"] == "developer"                            # -> Role Definition
    assert stored["capability_refs"] and stored["capability_refs"][0].startswith("CAP-")  # -> Capability SSOT
    assert len(prof.list_professional_roles(root, professional_domain_id=dom["domain_id"])) == 1


def test_professional_role_link_validation(tmp_path: Path) -> None:
    root = str(tmp_path)
    with pytest.raises(ValueError):
        prof.create_professional_role(root, professional_domain_id="PD-nope", name="X")
    dom = prof.create_professional_domain(root, name="Software Engineering")
    with pytest.raises(ValueError):
        prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                      name="X", role_ref="no-such-role")


def test_capability_not_implemented(tmp_path: Path) -> None:
    root = str(tmp_path)
    dom = prof.create_professional_domain(root, name="Data")
    prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                  name="Data Engineer", capability_refs=_caps(root, "etl"))
    # MU-CORE-07: Capability SSOT 落地; 但不实现 Plugin/Execution (无 ops/plugins)
    assert (tmp_path / "capability" / "capabilities.json").is_file()
    assert not (tmp_path / "ops" / "plugins").exists()


# ---------------------------------------------------------------- 11-12 边界

def test_company_boundary_preserved(tmp_path: Path) -> None:
    root = str(tmp_path)
    _, hid, _ = _company_and_identities(root)
    with pytest.raises(ValueError):     # 不存在的 Company scope 必须拒绝
        role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                    scope_type="company", scope_id="C-nope")
    with pytest.raises(ValueError):     # company scope 缺 scope_id
        role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                    scope_type="company")
    with pytest.raises(ValueError):     # global scope 不接受 scope_id (不臆造语义)
        role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                    scope_type="global", scope_id="C-1")


def test_identity_compatibility_preserved(tmp_path: Path) -> None:
    root = str(tmp_path)
    cid, hid, _ = _company_and_identities(root)
    role.create_role_assignment(root, identity_id=hid, role_id="developer",
                                scope_type="company", scope_id=cid)
    assert ident.get_identity(root, hid)["identity_type"] == "human"     # MU-02 语义不变
    assert ident.resolve_identity(root, hid)["identity_id"] == hid
    assert ident.resolve_actor_identity(root, hid) == hid


# ---------------------------------------------------------------- 运行时链路 (Company→Identity→Role→Professional→Capability contract)

def test_runtime_chain_company_identity_role_professional(tmp_path: Path) -> None:
    root = str(tmp_path)
    company = osco.create_company(root, name="Acme")
    employee_id = _hire_employee(root, company["id"])     # 真实链路: Employee -> Identity
    human = ident.project_employee(root, employee_id)
    assignment = role.create_role_assignment(root, identity_id=human["identity_id"],
                                             role_id="product-manager",
                                             scope_type="company",
                                             scope_id=company["id"])
    dom = prof.create_professional_domain(root, name="Software Engineering")
    prole = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                          name="Product Manager", role_ref="product-manager",
                                          capability_refs=_caps(root, "requirement", "planning"))
    resolved = role.resolve_identity_roles(root, human["identity_id"])
    assert assignment["role_id"] == "product-manager"
    assert resolved[0]["role"]["role_id"] == "product-manager"
    assert prole["professional_domain_id"] == dom["domain_id"]
    assert prole["capability_refs"] and prole["role_ref"] == "product-manager"


def _hire_employee(root: str, company_id: str) -> str:
    from org import lifecycle as org_lifecycle
    from org import store as org_store

    store = org_store.OrgStore(Path(root) / "org")
    lc = org_lifecycle.OrgLifecycle(store)
    role_ids = [r.id for r in store.list_roles_by_company(company_id)]
    emp = lc.hire_employee(company_id, "Alice", role_ids[0])
    return emp.id
