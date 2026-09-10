"""MU-CORE-08: Resolution（确定性解析服务）T1-T18。

Resolution 只解析: Work -> required capability -> ProfessionalRole -> Workforce -> Identity。
不执行 Plugin/Agent/Tool/Model, 不创建 Execution/TaskNode。
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

from factory_console import os_core_capability as cap  # noqa: E402
from factory_console import os_core_company_organization as osco  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console import os_core_professional as prof  # noqa: E402
from factory_console import os_core_project as proj  # noqa: E402
from factory_console import os_core_resolution as res  # noqa: E402
from factory_console import os_core_work as work  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402


def _capability(root: str, name: str = "Backend Development") -> str:
    return cap.create_capability(root, name=name, category="engineering")["capability_id"]


def _workforce_with_member(root: str, *, company_id: str, cap_id: str,
                           name: str = "Backend Team", status: str = "active") -> tuple[str, str]:
    wfk = wf.create_workforce(root, name=name, company_id=company_id, capability_refs=[cap_id])
    if status != "draft":
        wf.set_workforce_status(root, wfk["workforce_id"], status)
    person = ident.create_identity(root, identity_type="human", company_id=company_id,
                                   display_name=f"{name} lead")
    wf.add_member(root, wfk["workforce_id"], person["identity_id"],
                  professional_role_ref="")
    return wfk["workforce_id"], person["identity_id"]


def _fixture(root: str, *, company: str = "Acme", cap_name: str = "Backend Development"):
    company_id = osco.create_company(root, name=company)["id"]
    project = proj.create_project(root, name=f"{company} Project", company_id=company_id)
    cap_id = _capability(root, cap_name)
    dom = prof.create_professional_domain(root, name="Software Engineering")
    pr = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                       name="Backend Engineer", capability_refs=[cap_id])
    wf_id, idn = _workforce_with_member(root, company_id=company_id, cap_id=cap_id)
    w = work.create_work(root, project_id=project["id"], name="API Work",
                         required_capability_refs=[cap_id])
    return {"company": company_id, "project": project["id"], "capability": cap_id,
            "professional_role": pr["professional_role_id"], "workforce": wf_id,
            "identity": idn, "work": w["work_id"]}


# ---------------------------------------------------------------- T1-T7 主链

def test_t1_t7_work_to_identity_chain(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    # T1 resolution request 创建
    r = res.resolve_work(root, f["work"])
    assert r["resolution_id"].startswith("RS-") and r["status"] == "resolved"
    assert r["request"]["work_id"] == f["work"]
    m = r["matches"][0]
    assert m["capability_id"] == f["capability"]              # T2/T3
    assert m["professional_role_id"] == f["professional_role"]  # T4/T6
    assert m["workforce_id"] == f["workforce"]                # T5/T6
    assert m["identity_id"] == f["identity"]                  # T7
    assert "provides it" in m["reason"]                       # 可解释


def test_t13_reload_stable(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    r = res.resolve_work(root, f["work"])
    again = res.get_resolution(root, r["resolution_id"])
    assert again["resolution_id"] == r["resolution_id"] and again["status"] == "resolved"
    assert (tmp_path / "resolution" / "resolutions.json").is_file()


# ---------------------------------------------------------------- T8 Company isolation

def test_t8_company_isolation(tmp_path: Path) -> None:
    root = str(tmp_path)
    fa = _fixture(root, company="Company A")
    # Company B 有同 capability 的 active workforce, 但 A 的 work 不得选 B
    cb = osco.create_company(root, name="Company B")["id"]
    _workforce_with_member(root, company_id=cb, cap_id=fa["capability"], name="B Team")
    r = res.resolve_work(root, fa["work"])
    assert r["status"] == "resolved"
    assert all(m["workforce_id"] == fa["workforce"] for m in r["matches"])
    assert all(m["identity_id"] == fa["identity"] for m in r["matches"])


# ---------------------------------------------------------------- T9-T12 失败语义

def test_t9_retired_capability_unresolved(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    cap.set_capability_status(root, f["capability"], "retired")
    r = res.resolve_work(root, f["work"])
    assert r["status"] == "unresolved"
    assert f["capability"] in r["unresolved_capabilities"]


def test_t10_inactive_workforce_unresolved(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    wf.set_workforce_status(root, f["workforce"], "suspended")
    r = res.resolve_work(root, f["work"])
    assert r["status"] == "unresolved"
    assert "no eligible workforce" in r["reason"]


def test_t11_unknown_capability_unresolved(tmp_path: Path) -> None:
    root = str(tmp_path)
    company_id = osco.create_company(root, name="Acme")["id"]
    project = proj.create_project(root, name="P", company_id=company_id)
    w = work.create_work(root, project_id=project["id"], name="W")   # 无 required caps
    r = res.resolve_work(root, w["work_id"])
    assert r["status"] == "unresolved" and "no required capability" in r["reason"]
    r2 = res.resolve_capability(root, "CAP-nope", company_id=company_id)
    assert r2["status"] == "unresolved" and "CAP-nope" in r2["unresolved_capabilities"]


def test_t12_capability_without_workforce_unresolved(tmp_path: Path) -> None:
    root = str(tmp_path)
    company_id = osco.create_company(root, name="Acme")["id"]
    project = proj.create_project(root, name="P", company_id=company_id)
    cap_id = _capability(root, "Research")
    w = work.create_work(root, project_id=project["id"], name="W",
                         required_capability_refs=[cap_id])
    r = res.resolve_work(root, w["work_id"])
    assert r["status"] == "unresolved"
    assert cap_id in r["unresolved_capabilities"]
    assert "no eligible workforce" in r["reason"]


# ---------------------------------------------------------------- T14-T18 契约与边界

def test_t14_name_to_canonical_id(tmp_path: Path) -> None:
    root = str(tmp_path)
    company_id = osco.create_company(root, name="Acme")["id"]
    project = proj.create_project(root, name="P", company_id=company_id)
    cap.create_capability(root, name="Data Analysis")
    w = work.create_work(root, project_id=project["id"], name="W",
                         required_capability_refs=["Data Analysis"])   # name -> CAP-*
    assert w["required_capability_refs"][0].startswith("CAP-")
    with pytest.raises(ValueError):        # 无法解析的引用必须拒绝 (不 silent fallback)
        work.create_work(root, project_id=project["id"], name="Bad",
                         required_capability_refs=["No Such Cap"])


def test_t15_t16_no_second_store_and_no_execution(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    res.resolve_work(root, f["work"])
    assert not (tmp_path / "resolution" / "capabilities.json").exists()   # T15
    for d in ("execution", "executions", "task", "tasks", "nodes", "plugins"):
        assert not (tmp_path / d).exists()                                 # T16 未执行
    assert (tmp_path / "capability" / "capabilities.json").is_file()       # 引用 SSOT


def test_t17_t18_agent_and_industry_not_capability(tmp_path: Path) -> None:
    root = str(tmp_path)
    ident.create_identity(root, identity_type="agent", display_name="Agent X")
    assert cap.list_capabilities(root) == []                    # T17 Agent != Capability
    c = cap.create_capability(root, name="Supply Chain Planning")   # T18
    assert "industry_id" not in c and not (tmp_path / "org" / "capabilities.json").exists()
