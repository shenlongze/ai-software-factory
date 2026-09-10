"""factory-console/os_core_company_organization.py — OS Core Boundary: Company / Organization / Department.

MU-CORE-01: 本模块是 AI Factory OS 对 Company / Organization / Department Domain 的正式入口
(port/service)。职责边界:

- 只委托 factory-org/org 的 Company/Department SSOT (models/store/lifecycle);
- 不复制 store、不复制数据、不建立第二个数据存储、不重新实现 Company/Department;
- 跨域消费者 (workforce_os / Web API / CLI / runtime) 必须经本 boundary 访问组织事实。

不在本模块范围 (各自独立 Migration Unit):
Identity / Role / Professional Domain·Role / Industry / Capability / Plugin / Work / FactorySpec。

API:
    create_company(root, *, name, template="solo", company_id=None) -> dict
    get_company(root, company_id) -> dict | None
    list_companies(root) -> list[dict]
    create_department(root, *, company_id, name, department_id=None) -> dict
    get_department(root, department_id) -> dict | None
    list_departments(root, company_id="") -> list[dict]
    resolve_org_id(root, ref="", *, name="") -> str
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORG_SRC = _REPO_ROOT / "factory-org"


def _org_modules() -> tuple[Any, Any]:
    """导入 factory-org/org (源码态需挂 sys.path; 安装态可直接 import org)。"""
    try:
        from org import lifecycle as org_lifecycle
        from org import store as org_store
    except ModuleNotFoundError:  # 源码态 (仓库内直接运行)
        src = str(_ORG_SRC)
        if src not in sys.path:
            sys.path.insert(0, src)
        from org import lifecycle as org_lifecycle
        from org import store as org_store
    return org_lifecycle, org_store


def _org_store(root: str | Path) -> Any:
    _, org_store = _org_modules()
    return org_store.OrgStore(Path(root) / "org")


def _lifecycle(root: str | Path) -> Any:
    org_lifecycle, _ = _org_modules()
    return org_lifecycle.OrgLifecycle(_org_store(root))


# ---------------------------------------------------------------- Company

def create_company(root: str | Path, *, name: str, template: str = "solo",
                   company_id: str | None = None) -> dict[str, Any]:
    """创建 Company (OS Organization 根): 委托 org SSOT 的模板化生命周期。"""
    company = _lifecycle(root).create_company(name, template=template,
                                              company_id=company_id)
    return company.to_dict()


def get_company(root: str | Path, company_id: str) -> dict[str, Any] | None:
    company = _org_store(root).get_company(str(company_id))
    return company.to_dict() if company is not None else None


def list_companies(root: str | Path) -> list[dict[str, Any]]:
    return [c.to_dict() for c in _org_store(root).list_companies()]


def resolve_org_id(root: str | Path, ref: str = "", *, name: str = "") -> str:
    """解析规范 org_id (统一入口)。

    优先级: ref 命中 company id -> ref 命中 company name -> name 命中
            -> 唯一公司(无参数) -> 否则 ValueError。
    """
    companies = _org_store(root).list_companies()
    ref = str(ref or "")
    name = str(name or "")
    for c in companies:
        if ref and c.id == ref:
            return str(c.id)
    for c in companies:
        if ref and c.name == ref:
            return str(c.id)
    for c in companies:
        if name and c.name == name:
            return str(c.id)
    if len(companies) == 1 and not ref and not name:
        return str(companies[0].id)
    raise ValueError(f"无法解析 org_id: ref={ref!r} name={name!r}")


# ---------------------------------------------------------------- Department

def create_department(root: str | Path, *, company_id: str, name: str,
                      department_id: str | None = None) -> dict[str, Any]:
    """创建 Department (Company 直属子节点); company 必须存在 (否则 ValueError)。"""
    store = _org_store(root)
    if store.get_company(str(company_id)) is None:
        raise ValueError(f"Company 不存在: {company_id}")
    dept = _lifecycle(root).create_department(str(company_id), name,
                                              department_id=department_id)
    return dept.to_dict()


def get_department(root: str | Path, department_id: str) -> dict[str, Any] | None:
    dept = _org_store(root).get_department(str(department_id))
    return dept.to_dict() if dept is not None else None


def list_departments(root: str | Path, company_id: str = "") -> list[dict[str, Any]]:
    store = _org_store(root)
    if company_id:
        return [d.to_dict() for d in store.list_departments_by_company(str(company_id))]
    return [d.to_dict() for d in store.list_departments()]


__all__ = [
    "create_company",
    "create_department",
    "get_company",
    "get_department",
    "list_companies",
    "list_departments",
    "resolve_org_id",
]
