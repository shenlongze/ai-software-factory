"""MU-CORE-01: OS Core Company/Organization Boundary + workforce_os 单真相测试。

验收目标:
1. Boundary 是 Company/Department 的正式入口 (委托 org SSOT, 不复制 store)。
2. workforce_os 不再产生第二组织真相 (organizations/departments 不落 ops/workforce_os)。
3. org_id 统一 (workforce_os 返回的 org_id == org SSOT company id)。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-org")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import os_core_company_organization as osco  # noqa: E402
from factory_console import workforce_os as wfos  # noqa: E402


def test_boundary_company_crud(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = osco.create_company(root, name="Acme")
    assert c["name"] == "Acme"
    assert (Path(root) / "org" / "companies.json").is_file()  # 事实在 org SSOT
    assert osco.get_company(root, c["id"])["name"] == "Acme"
    assert [x["id"] for x in osco.list_companies(root)] == [c["id"]]
    assert osco.get_company(root, "C-not-exist") is None


def test_boundary_department(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = osco.create_company(root, name="Acme")
    d = osco.create_department(root, company_id=c["id"], name="Engineering")
    assert d["company_id"] == c["id"]
    assert osco.get_department(root, d["id"])["name"] == "Engineering"
    ids = [x["id"] for x in osco.list_departments(root, company_id=c["id"])]
    assert d["id"] in ids


def test_boundary_department_unknown_company(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        osco.create_department(str(tmp_path), company_id="C-nope", name="X")


def test_resolve_org_id(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = osco.create_company(root, name="Acme")
    assert osco.resolve_org_id(root, c["id"]) == c["id"]
    assert osco.resolve_org_id(root, "Acme") == c["id"]
    assert osco.resolve_org_id(root, name="Acme") == c["id"]
    assert osco.resolve_org_id(root) == c["id"]  # 唯一公司


def test_workforce_os_delegates_to_org_ssot(tmp_path: Path) -> None:
    root = str(tmp_path)
    org = wfos.create_organization(root, name="Acme")
    # 1) 事实落在 org SSOT
    assert osco.get_company(root, org["org_id"]) is not None
    # 2) 不再产生第二组织真相
    assert not (Path(root) / "ops" / "workforce_os" / "organizations.json").exists()

    dept = wfos.create_department(root, org_id=org["org_id"], name="Engineering")
    assert osco.get_department(root, dept["dept_id"]) is not None
    assert not (Path(root) / "ops" / "workforce_os" / "departments.json").exists()

    # 3) 视图同源: list_organizations 从 org SSOT 投影
    listed = wfos.list_organizations(root)
    assert len(listed) == 1
    assert listed[0]["org_id"] == org["org_id"]
    assert dept["dept_id"] in listed[0]["departments"]


def test_workforce_os_unknown_org(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        wfos.create_department(str(tmp_path), org_id="org-none", name="X")
