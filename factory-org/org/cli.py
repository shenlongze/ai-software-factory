"""factory-org/org/cli.py — 组织 CLI (`factory-org` console script + 主 CLI 共享命令)。

命令 (Phase 16A 任务清单):
```
factory-org company create --template software_company --name X
factory-org company show <company_id>
factory-org employee hire --company X --role developer --capabilities python,java
factory-org employee list [--company X] [--role R] [--capability C]
factory-org authority check --role developer --permission release.approve
factory-org knowledge add --company X --domain docs --content "..."
factory-org knowledge list --company X
```

架构:
- cmd_* 函数签名 (root: Path, args) → dict — 主 CLI (factory-core/cli) 延迟
  import 本模块后复用同一实现 (org 命令并入主 CLI, 单一实现零复制)。
- 每命令在 logger_scope 内打开事件库 (root/factory.db) + EventLogger,
  event_seq 在块内取 (WAL 关闭陷阱, 同 factory CLI 模式)。
- 错误映射: NotFoundError → exit_code 7 (未找到), 其余业务错误 → 1;
  cmd_* 捕获返回错误 dict, 不抛 (双 CLI 复用, 零异常管道)。
- --role 接受角色 id 或角色名 (大小写不敏感, 模板角色名 Developer ↔
  --role developer); --employee 接受员工 id。
- 只读命令发审计事件 (ADR-0002: 所有 CLI 行为必须产生 Event)。

Removal Isolation: 本模块只依赖 factory-core events 层 (Extension → Core
单向依赖); factory-core 零顶层 imports 本包。
"""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from events.logger import EventLogger
from events.models import EventType
from events.store import EventStore

from . import events as org_events
from .lifecycle import (
    CompanyMismatchError,
    DuplicateError,
    NotFoundError,
    OrgLifecycle,
    OrgLifecycleError,
    RoleConflictError,
)
from .models import new_id
from .store import OrgStore

DEFAULT_ROOT = Path.home() / ".factory"


@contextmanager
def _logger_scope(root: Path) -> Iterator[EventLogger]:
    """打开事件库 + EventLogger 作用域 (退出关闭连接, 同 ctx.logger_scope)。"""
    store = EventStore(root / "factory.db")
    try:
        yield EventLogger(store)
    finally:
        store.close()


def _org_store(root: Path) -> OrgStore:
    return OrgStore(root / "org")


def _resolve_role_id(
    store: OrgStore, company_id: str | None, role_ref: str
) -> str:
    """角色引用 → 角色 id (S7-001 统一解析, 大小写不敏感)。

    有 company 作用域 → 委托 OrgLifecycle.resolve_role_ref (3 链: id 精确 /
    公司内名称大小写不敏感 / exec 注册表 role_ref 匹配 — 双体系统一);
    无 company → 全局 id/名称匹配 (employee list 全库过滤场景)。

    未找到 → NotFoundError (CLI 层错误映射 rc 7)。
    """
    if company_id is not None:
        return OrgLifecycle(store).resolve_role_ref(company_id, role_ref)
    if store.get_role(role_ref) is not None:
        return role_ref
    for role in store.list_roles():
        if role.name.strip().lower() == role_ref.strip().lower():
            return role.id
    raise NotFoundError(f"role not found: {role_ref!r}")


def _error(message: str, exit_code: int = 1) -> dict:
    return {"ok": False, "error": message, "exit_code": exit_code}


def _capabilities(args: Any) -> list[str]:
    raw = getattr(args, "capabilities", None) or ""
    return [c.strip() for c in raw.split(",") if c.strip()]


# ------------------------------------------------------------------ company

def cmd_company_create(root: Path, args: Any) -> dict:
    """company create — 模板实例化公司 (org.company.created 链事件)。"""
    with _logger_scope(root) as logger:
        try:
            company = OrgLifecycle(_org_store(root), logger=logger).create_company(
                args.name,
                template=getattr(args, "template", "solo") or "solo",
                company_id=getattr(args, "id", None),
            )
        except OrgLifecycleError as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_COMPANY_CREATED)
    return {
        "ok": True,
        "company": company.to_dict(),
        "department_count": len(company.departments),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def cmd_company_show(root: Path, args: Any) -> dict:
    """company show — 公司详情 + 部门/角色 (org.company.viewed 审计)。"""
    with _logger_scope(root) as logger:
        try:
            lifecycle = OrgLifecycle(_org_store(root), logger=logger)
            company = lifecycle.get_company(args.company_id)
        except OrgLifecycleError as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        departments = _org_store(root).list_departments_by_company(company.id)
        roles = _org_store(root).list_roles_by_company(company.id)
        org_events.record_company_viewed(logger, company=company)
        event_seq = org_events.last_seq(logger, EventType.ORG_COMPANY_VIEWED)
    return {
        "ok": True,
        "company": company.to_dict(),
        "departments": [d.to_dict() for d in departments],
        "roles": [r.to_dict() for r in roles],
        "event_seq": event_seq,
        "exit_code": 0,
    }


# ------------------------------------------------------------------ employee

def cmd_employee_hire(root: Path, args: Any) -> dict:
    """employee hire — 入职 (org.employee.joined → role_assigned → capability_added)。"""
    with _logger_scope(root) as logger:
        store = _org_store(root)
        lifecycle = OrgLifecycle(store, logger=logger)
        try:
            role_id = _resolve_role_id(store, args.company, args.role)
            employee = lifecycle.hire_employee(
                args.company,
                getattr(args, "name", None) or new_id("E"),
                role_id,
                capabilities=_capabilities(args),
                employee_id=getattr(args, "id", None),
            )
        except (OrgLifecycleError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_EMPLOYEE_JOINED)
    return {
        "ok": True,
        "employee": employee.to_dict(),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def cmd_employee_list(root: Path, args: Any) -> dict:
    """employee list — 员工清单 (按角色/能力过滤; org.employee.viewed 审计)。"""
    with _logger_scope(root) as logger:
        store = _org_store(root)
        try:
            role_id = None
            if getattr(args, "role", None):
                role_id = _resolve_role_id(store, getattr(args, "company", None), args.role)
            employees = OrgLifecycle(store, logger=logger).find_employees(
                company_id=getattr(args, "company", None),
                capability=getattr(args, "capability", None),
                role_id=role_id,
            )
        except OrgLifecycleError as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        org_events.record_employee_viewed(logger, count=len(employees))
        event_seq = org_events.last_seq(logger, EventType.ORG_EMPLOYEE_VIEWED)
    return {
        "ok": True,
        "employees": [e.to_dict() for e in employees],
        "count": len(employees),
        "event_seq": event_seq,
        "exit_code": 0,
    }


# ------------------------------------------------------------------ authority

def cmd_authority_check(root: Path, args: Any) -> dict:
    """authority check — 权限校验 (Default Deny; org.authority.checked 审计)。

    --employee EID 按员工角色集校验; --role ROLE 按单一角色校验
    (--company 可选, 用于角色名解析域)。
    """
    with _logger_scope(root) as logger:
        store = _org_store(root)
        lifecycle = OrgLifecycle(store, logger=logger)
        try:
            if getattr(args, "employee", None):
                allowed = lifecycle.check_authority(args.employee, args.permission)
                employee = store.get_employee(args.employee)
                role_ids = list(employee.role_ids) if employee else []
            else:
                role_id = _resolve_role_id(store, getattr(args, "company", None), args.role)
                allowed = lifecycle.check_authority_for_roles([role_id], args.permission)
                org_events.record_authority_checked(
                    logger,
                    permission=args.permission,
                    allowed=allowed,
                    role_ids=[role_id],
                )
                role_ids = [role_id]
        except (OrgLifecycleError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_AUTHORITY_CHECKED)
    return {
        "ok": True,
        "permission": args.permission,
        "role_ids": role_ids,
        "allowed": allowed,
        "result": "ALLOW" if allowed else "DENY",
        "event_seq": event_seq,
        "exit_code": 0,
    }


# ------------------------------------------------------------------ knowledge

def cmd_knowledge_add(root: Path, args: Any) -> dict:
    """knowledge add — 知识入库 (org.knowledge.bound; 公司隔离)。"""
    with _logger_scope(root) as logger:
        try:
            item = OrgLifecycle(_org_store(root), logger=logger).add_knowledge(
                args.company,
                args.domain,
                args.content,
                knowledge_id=getattr(args, "id", None),
            )
        except OrgLifecycleError as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_KNOWLEDGE_BOUND)
    return {
        "ok": True,
        "knowledge": item.to_dict(),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def cmd_knowledge_list(root: Path, args: Any) -> dict:
    """knowledge list — 公司知识清单 (org.knowledge.viewed 审计; 公司隔离)。"""
    with _logger_scope(root) as logger:
        store = _org_store(root)
        items = store.list_knowledge_by_company(args.company)
        org_events.record_knowledge_viewed(logger, count=len(items))
        event_seq = org_events.last_seq(logger, EventType.ORG_KNOWLEDGE_VIEWED)
    return {
        "ok": True,
        "company_id": args.company,
        "knowledge": [k.to_dict() for k in items],
        "count": len(items),
        "event_seq": event_seq,
        "exit_code": 0,
    }


# ------------------------------------------------------------------ 独立 CLI (factory-org console script)

def build_parser() -> argparse.ArgumentParser:
    """factory-org [--root DIR] [--json] <command> ... (与主 CLI org 同构)。"""
    p = argparse.ArgumentParser(
        prog="factory-org",
        description="AI Software Factory — 组织扩展 CLI (Company/Employee/Authority/Knowledge)",
    )
    p.add_argument("--root", default=None, help=f"工厂根目录 (默认: {DEFAULT_ROOT})")
    p.add_argument("--json", action="store_true", help="输出 JSON (脚本消费)")
    sub = p.add_subparsers(dest="command", required=True)

    def json_opt(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)

    p_company = sub.add_parser("company", help="公司管理 (org.company.* 事件)")
    json_opt(p_company)
    csub = p_company.add_subparsers(dest="company_command", required=True)
    p_cc = csub.add_parser("create", help="模板实例化公司 (发 org.company.created)")
    json_opt(p_cc)
    p_cc.add_argument("--template", default="solo", choices=["software_company", "solo"],
                      help="公司模板 (默认 solo)")
    p_cc.add_argument("--name", required=True, help="公司名称")
    p_cc.add_argument("--id", default=None, help="公司 ID (默认自动生成 C-xxx)")
    p_cs = csub.add_parser("show", help="公司详情 + 部门/角色 (发 org.company.viewed)")
    json_opt(p_cs)
    p_cs.add_argument("company_id")

    p_emp = sub.add_parser("employee", help="员工管理 (org.employee.* 事件)")
    json_opt(p_emp)
    esub = p_emp.add_subparsers(dest="employee_command", required=True)
    p_eh = esub.add_parser("hire", help="员工入职 (发 org.employee.joined)")
    json_opt(p_eh)
    p_eh.add_argument("--company", required=True, help="公司 ID")
    p_eh.add_argument("--role", required=True, help="角色 id 或名称 (如 developer)")
    p_eh.add_argument("--capabilities", default="", help="能力列表, 逗号分隔 (如 python,java)")
    p_eh.add_argument("--name", default=None, help="员工姓名 (默认自动生成)")
    p_eh.add_argument("--id", default=None, help="员工 ID (默认自动生成 E-xxx)")
    p_el = esub.add_parser("list", help="员工清单 (发 org.employee.viewed)")
    json_opt(p_el)
    p_el.add_argument("--company", default=None, help="按公司过滤")
    p_el.add_argument("--role", default=None, help="按角色过滤 (id 或名称)")
    p_el.add_argument("--capability", default=None, help="按能力过滤")

    p_auth = sub.add_parser("authority", help="权限校验 (Default Deny)")
    json_opt(p_auth)
    asub = p_auth.add_subparsers(dest="authority_command", required=True)
    p_ac = asub.add_parser("check", help="权限校验 (发 org.authority.checked)")
    json_opt(p_ac)
    p_ac.add_argument("--employee", default=None, help="员工 ID (按员工角色集校验)")
    p_ac.add_argument("--role", default=None, help="角色 id 或名称 (按单一角色校验)")
    p_ac.add_argument("--company", default=None, help="角色名解析域 (可选)")
    p_ac.add_argument("--permission", required=True, help="权限 (如 release.approve)")

    p_kn = sub.add_parser("knowledge", help="企业知识管理 (org.knowledge.* 事件)")
    json_opt(p_kn)
    ksub = p_kn.add_subparsers(dest="knowledge_command", required=True)
    p_ka = ksub.add_parser("add", help="知识入库 (发 org.knowledge.bound)")
    json_opt(p_ka)
    p_ka.add_argument("--company", required=True, help="公司 ID (知识隔离)") 
    p_ka.add_argument("--domain", required=True, help="知识域 (如 docs/tech/sop)")
    p_ka.add_argument("--content", required=True, help="知识内容")
    p_ka.add_argument("--id", default=None, help="知识 ID (默认自动生成 K-xxx)")
    p_kl = ksub.add_parser("list", help="公司知识清单 (发 org.knowledge.viewed)")
    json_opt(p_kl)
    p_kl.add_argument("--company", required=True, help="公司 ID")
    return p


_CMD_DISPATCH: dict[str, dict[str, Any]] = {
    "company": {
        "create": cmd_company_create,
        "show": cmd_company_show,
    },
    "employee": {
        "hire": cmd_employee_hire,
        "list": cmd_employee_list,
    },
    "authority": {
        "check": cmd_authority_check,
    },
    "knowledge": {
        "add": cmd_knowledge_add,
        "list": cmd_knowledge_list,
    },
}


def _dispatch(root: Path, args: Any) -> dict:
    sub = getattr(args, f"{args.command}_command", None) or ""
    fn = _CMD_DISPATCH.get(args.command, {}).get(sub)
    if fn is None:
        return _error(f"unknown command: {args.command} {sub}", exit_code=2)
    return fn(root, args)


def _print_result(args: Any, result: dict) -> None:
    if args.json:
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not result.get("ok"):
        print(f"error: {result.get('error')}", file=sys.stderr)
        return
    command = args.command
    if command == "company":
        company = result["company"]
        if args.company_command == "create":
            print("✔ 公司创建成功 (模板实例化)")
            print(f"  id          {company['id']}")
            print(f"  name        {company['name']}")
            print(f"  template    {company['template']}")
            print(f"  departments {result['department_count']}")
        else:
            print(f"公司 {company['id']} — {company['name']} (模板: {company['template']})")
            for dept in result["departments"]:
                print(f"  部门  {dept['name']} ({dept['id']})")
            for role in result["roles"]:
                human = " [Human]" if role.get("human") else ""
                print(f"  角色  {role['name']} ({role['id']}){human}")
        if result.get("event_seq") is not None:
            print(f"  event_seq   {result['event_seq']}")
    elif command == "employee":
        if args.employee_command == "hire":
            emp = result["employee"]
            print("✔ 员工入职")
            print(f"  id        {emp['id']}")
            print(f"  name      {emp['name']}")
            print(f"  company   {emp['company_id']}")
            print(f"  roles     {', '.join(emp['role_ids'])}")
            print(f"  caps      {', '.join(emp['capabilities']) or '(无)'}")
            if result.get("event_seq") is not None:
                print(f"  event_seq {result['event_seq']}")
        else:
            print(f"员工清单 ({result['count']} 人)")
            for emp in result["employees"]:
                print(f"  {emp['id']}  {emp['name']}  {emp['company_id']}  "
                      f"roles={len(emp['role_ids'])} caps={len(emp['capabilities'])}")
    elif command == "authority":
        print(f"权限校验: {result['permission']} → {result['result']}")
        print(f"  roles     {', '.join(result['role_ids'])}")
        if result.get("event_seq") is not None:
            print(f"  event_seq {result['event_seq']}")
    elif command == "knowledge":
        if args.knowledge_command == "add":
            item = result["knowledge"]
            print("✔ 知识入库 (公司隔离)")
            print(f"  id        {item['id']}")
            print(f"  company   {item['company_id']}")
            print(f"  domain    {item['domain']}")
            print(f"  version   {item['version']}")
            if result.get("event_seq") is not None:
                print(f"  event_seq {result['event_seq']}")
        else:
            print(f"知识清单 ({result['count']} 条) — 公司 {result['company_id']}")
            for item in result["knowledge"]:
                print(f"  {item['id']}  [{item['domain']}] v{item['version']}  {item['content']}")


def main(argv: list[str] | None = None) -> int:
    """factory-org CLI 入口 (console script `factory-org` 以返回值作退出码)。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else DEFAULT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    result = _dispatch(root, args)
    exit_code = int(result.get("exit_code", 0))
    if exit_code != 2:
        _print_result(args, result)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
