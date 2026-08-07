"""factory-org/org/store.py — 组织独立数据空间 (原子写, 损坏失败安全)。

设计依据 (phase16-organization-model-review.md §6):
```
factory-org/ (Phase 16A Extension):
  store: 独立数据空间 <root>/org/ (companies/departments/roles/employees/
         authorities/knowledge.json) — 与 tasks/agents/product/intelligence
         等数据空间完全分离; 删除 factory-org 不影响 Factory (Core 零感知)
```

文件布局 (每实体单文件单节, 与 intelligence store 同构):
```
<root>/org/
├── companies.json     {"companies": {id: Company dict}}
├── departments.json   {"departments": {id: Department dict}}
├── roles.json         {"roles": {id: Role dict}}
├── employees.json     {"employees": {id: Employee dict}}
├── authorities.json   {"authorities": {id: Authority dict}}
└── knowledge.json     {"knowledge": {id: KnowledgeItem dict}}
```

损坏语义 (同 ProductStore/IntelligenceStore): 核心目录数据损坏 → 响亮
CorruptOrgStoreError (绝不静默返回空); 原子写 = 临时文件 + os.replace。
本模块只做持久化 (读/写整库), 无业务逻辑; **零顶层 imports events**
(Removal Isolation, 同 provider/product store 模式); 只依赖 stdlib +
pydantic + 本层 models。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .models import Authority, Company, Department, Employee, KnowledgeItem, Role

T = TypeVar("T", bound=BaseModel)


class OrgStoreError(Exception):
    """OrgStore 基础异常。"""


class CorruptOrgStoreError(OrgStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class ConflictError(OrgStoreError):
    """数据冲突 (重复 id 等 — 唯一性约束)。"""


class _SectionStore(Generic[T]):
    """单实体 JSON 记录库基类 (原子写/损坏失败安全; 子类声明类属性即可)。"""

    _filename: str
    _section: str
    _model: type[T]

    def __init__(self, org_dir: str | Path):
        self._dir = Path(org_dir)

    @property
    def dir(self) -> Path:
        """数据空间目录 (<root>/org)。"""
        return self._dir

    # ------------------------------------------------------------------ 读

    def _path(self) -> Path:
        return self._dir / self._filename

    def _read_all(self) -> dict[str, dict[str, Any]]:
        """读整库 {id: dict}; 文件不存在返回空库 (首次写前合法状态)。"""
        path = self._path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptOrgStoreError(
                f"corrupt org store: {path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get(self._section), dict):
            raise CorruptOrgStoreError(
                f"corrupt org store: {path}: missing or invalid section "
                f"{self._section!r}"
            )
        return raw[self._section]

    def _load(self, data: Any) -> T:
        try:
            return self._model.model_validate(data)
        except ValidationError as exc:
            raise CorruptOrgStoreError(
                f"corrupt org store: {self._path()}: {exc}"
            ) from exc

    # ------------------------------------------------------------------ 写

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        """原子写单文件: 临时文件 + os.replace (同目录, 同文件系统原子性)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path()
        tmp = self._dir / f".{self._filename}.{os.getpid()}.tmp"
        payload = {self._section: dict(sorted(records.items()))}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ------------------------------------------------------------------ 通用 API

    def save(self, record: T) -> None:
        """upsert 记录 (同 id 覆盖 = 状态流转经 model_copy 新实例后落库)。"""
        records = self._read_all()
        records[record.id] = record.to_dict()  # type: ignore[attr-defined]
        self._write(records)

    def get(self, record_id: str) -> T | None:
        """按 id 取记录; 不存在返回 None。"""
        data = self._read_all().get(record_id)
        if data is None:
            return None
        return self._load(data)

    def list_all(self) -> list[T]:
        """全部记录 (按 id 排序, 审计友好)。"""
        return sorted(
            (self._load(data) for data in self._read_all().values()),
            key=lambda r: r.id,  # type: ignore[attr-defined, return-value]
        )

    def count(self) -> int:
        """记录总数。"""
        return len(self._read_all())

    def delete(self, record_id: str) -> bool:
        """删除记录; 不存在返回 False (幂等)。"""
        records = self._read_all()
        if record_id not in records:
            return False
        del records[record_id]
        self._write(records)
        return True


class CompanyStore(_SectionStore[Company]):
    """Company 持久化 (companies.json)。"""

    _filename = "companies.json"
    _section = "companies"
    _model = Company


class DepartmentStore(_SectionStore[Department]):
    """Department 持久化 (departments.json)。"""

    _filename = "departments.json"
    _section = "departments"
    _model = Department


class RoleStore(_SectionStore[Role]):
    """Role 持久化 (roles.json)。"""

    _filename = "roles.json"
    _section = "roles"
    _model = Role


class EmployeeStore(_SectionStore[Employee]):
    """Employee 持久化 (employees.json)。"""

    _filename = "employees.json"
    _section = "employees"
    _model = Employee


class AuthorityStore(_SectionStore[Authority]):
    """Authority 持久化 (authorities.json)。"""

    _filename = "authorities.json"
    _section = "authorities"
    _model = Authority


class KnowledgeStore(_SectionStore[KnowledgeItem]):
    """KnowledgeItem 持久化 (knowledge.json)。"""

    _filename = "knowledge.json"
    _section = "knowledge"
    _model = KnowledgeItem


class OrgStore:
    """组织数据空间门面: 六实体子库 (companies/departments/roles/employees/
    authorities/knowledge) 共享 <root>/org/ 目录, 互不依赖 (一个文件损坏
    不影响另外五个)。

    只做持久化 + 实体维度查询; 引用完整性校验在 OrgLifecycle 层 (store
    保持哑持久化, 生命周期层编排)。
    """

    def __init__(self, org_dir: str | Path):
        self._dir = Path(org_dir)
        self._companies = CompanyStore(self._dir)
        self._departments = DepartmentStore(self._dir)
        self._roles = RoleStore(self._dir)
        self._employees = EmployeeStore(self._dir)
        self._authorities = AuthorityStore(self._dir)
        self._knowledge = KnowledgeStore(self._dir)

    @property
    def dir(self) -> Path:
        return self._dir

    # ------------------------------------------------------------------ Company

    def save_company(self, company: Company) -> None:
        self._companies.save(company)

    def get_company(self, company_id: str) -> Company | None:
        return self._companies.get(company_id)

    def list_companies(self) -> list[Company]:
        return self._companies.list_all()

    def count_companies(self) -> int:
        return self._companies.count()

    # ------------------------------------------------------------------ Department

    def save_department(self, department: Department) -> None:
        self._departments.save(department)

    def get_department(self, department_id: str) -> Department | None:
        return self._departments.get(department_id)

    def list_departments(self) -> list[Department]:
        return self._departments.list_all()

    def list_departments_by_company(self, company_id: str) -> list[Department]:
        return [d for d in self.list_departments() if d.company_id == company_id]

    # ------------------------------------------------------------------ Role

    def save_role(self, role: Role) -> None:
        self._roles.save(role)

    def get_role(self, role_id: str) -> Role | None:
        return self._roles.get(role_id)

    def list_roles(self) -> list[Role]:
        return self._roles.list_all()

    def list_roles_by_company(self, company_id: str) -> list[Role]:
        return [r for r in self.list_roles() if r.company_id == company_id]

    def list_roles_by_department(self, department_id: str) -> list[Role]:
        return [r for r in self.list_roles() if r.department_id == department_id]

    # ------------------------------------------------------------------ Employee

    def save_employee(self, employee: Employee) -> None:
        self._employees.save(employee)

    def get_employee(self, employee_id: str) -> Employee | None:
        return self._employees.get(employee_id)

    def list_employees(self) -> list[Employee]:
        return self._employees.list_all()

    def list_employees_by_company(self, company_id: str) -> list[Employee]:
        return [e for e in self.list_employees() if e.company_id == company_id]

    # ------------------------------------------------------------------ Authority

    def save_authority(self, authority: Authority) -> None:
        self._authorities.save(authority)

    def get_authority(self, authority_id: str) -> Authority | None:
        return self._authorities.get(authority_id)

    def list_authorities(self) -> list[Authority]:
        return self._authorities.list_all()

    def list_authorities_by_role(self, role_id: str) -> list[Authority]:
        return [a for a in self.list_authorities() if a.role_id == role_id]

    def delete_authority(self, authority_id: str) -> bool:
        """删除权限记录 (grant/deny last-write-wins 前置); 不存在返回 False。"""
        return self._authorities.delete(authority_id)

    # ------------------------------------------------------------------ Knowledge

    def save_knowledge(self, item: KnowledgeItem) -> None:
        self._knowledge.save(item)

    def get_knowledge(self, knowledge_id: str) -> KnowledgeItem | None:
        return self._knowledge.get(knowledge_id)

    def list_knowledge(self) -> list[KnowledgeItem]:
        return self._knowledge.list_all()

    def list_knowledge_by_company(self, company_id: str) -> list[KnowledgeItem]:
        return [k for k in self.list_knowledge() if k.company_id == company_id]

    # ------------------------------------------------------------------ 数据空间

    def files(self) -> list[Path]:
        """六个数据文件 (存在者; 测试/审计用)。"""
        return sorted(
            p
            for p in (
                self._dir / "companies.json",
                self._dir / "departments.json",
                self._dir / "roles.json",
                self._dir / "employees.json",
                self._dir / "authorities.json",
                self._dir / "knowledge.json",
            )
            if p.exists()
        )
