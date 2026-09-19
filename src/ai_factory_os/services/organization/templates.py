"""src/legacy/factory-org/org/templates.py — company 模板 + Role 冲突规则。

设计依据 (ai-company-operating-model.md §1/§2):
- Company Template → 实例化: 模板 = Organization + Role + Policy (声明式)
- software_company (MarkPad AI Software Company): Department Product/
  Engineering/Quality; Roles CEO(Human)/PM/Architect/Developer/QA(AI)
- Solo 模式同一模型: 扁平 (Company→Roles, 无部门), 角色集同 5 个
  (Solo 无 Board/VP, 但 CEO 存在 — Human, 一人兼多职)

权限模型 (ai-company-operating-model.md §3, Default Deny):
- Authority 绑定 Role, 未声明 = 拒绝; 高危 (release.approve) 默认 deny —
  Developer 无 release.approve 记录 → 硬拒绝
- 执行权 != 审核权: 冲突组合注册表硬拒绝 (Developer+Reviewer/QA, 任何+CEO)

模板实例化 (OrgLifecycle.create_company) 物化: 部门 → 角色 → 权限记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TemplateError(Exception):
    """模板层异常。"""


class TemplateNotFoundError(TemplateError):
    """模板 id 未注册。"""


@dataclass(frozen=True)
class RoleSpec:
    """模板中的角色定义 (department="" = company-level, Solo 扁平)。

    role_ref: 统一角色注册表引用 (S7-001: exec/roles.py 为事实源) — exec
    注册表 role_id (如 "developer"/"tester"), 或 "" = 无执行角色
    (Human CEO — 最终批准权唯一, 非 Agent)。org 模板角色经 role_ref 指向
    单一注册表, 消除 org 模板 vs exec roles.py 双角色体系 (审计风险)。
    向后兼容: 缺省 "", 既有模板/测试构造零影响。
    """

    name: str
    department: str = ""
    responsibility: str = ""
    authority_policy: dict[str, str] = field(default_factory=dict)
    human: bool = False
    role_ref: str = ""


@dataclass(frozen=True)
class CompanyTemplate:
    """声明式公司模板 (Organization + Role + Policy)。"""

    template_id: str
    name: str
    description: str
    departments: tuple[str, ...] = ()
    roles: tuple[RoleSpec, ...] = ()


# ------------------------------------------------------------------ 冲突规则
# 执行权 != 审核权: 以下组合禁 (employee 多角色并集校验, 硬拒绝)。
# ("*", "ceo") = 任何角色 + CEO 不可兼任 (最终批准权唯一, Human CEO)。

FORBIDDEN_ROLE_COMBINATIONS: tuple[tuple[str, str], ...] = (
    ("developer", "reviewer"),
    ("developer", "qa"),
    ("*", "ceo"),
)


def check_role_conflict(existing_role_names: list[str], new_role_name: str) -> str | None:
    """检测角色冲突组合; 无冲突返回 None, 有冲突返回冲突描述。

    归一: 小写 + 去空白 (role name "Developer" ↔ 规则 "developer")。
    "*" 通配任意角色名。组合顺序无关 (Developer+QA 与 QA+Developer 都拒)。
    """
    names = {str(n).strip().lower() for n in existing_role_names}
    names.add(str(new_role_name).strip().lower())
    for a, b in FORBIDDEN_ROLE_COMBINATIONS:
        a_n, b_n = a.lower(), b.lower()
        if a_n == "*" and b_n in names:
            return f"Role conflict: {new_role_name} + CEO 不可兼任 (最终批准权唯一)"
        if b_n == "*" and a_n in names:
            return f"Role conflict: {new_role_name} + CEO 不可兼任 (最终批准权唯一)"
        if a_n in names and b_n in names:
            return (
                f"Role conflict: {a_n} + {b_n} 冲突组合 (执行权 != 审核权, "
                f"禁兼任)"
            )
    return None


# ------------------------------------------------------------------ software_company 模板

SOFTWARE_COMPANY: CompanyTemplate = CompanyTemplate(
    template_id="software_company",
    name="MarkPad AI Software Company",
    description=(
        "AI Software Company: Human CEO + PM/Architect/Developer/QA AI 员工; "
        "Default Deny (高危 release.approve 仅 CEO)"
    ),
    departments=("Product", "Engineering", "Quality"),
    roles=(
        RoleSpec(
            name="CEO",
            department="Product",
            human=True,
            responsibility="公司方向与最终批准权 (Human, 唯一最终权)",
            authority_policy={
                "company.manage": "allow",
                "employee.hire": "allow",
                "release.approve": "allow",
            },
        ),
        RoleSpec(
            name="Product Manager",
            department="Product",
            responsibility="需求分析/计划/调度 (PM ≠ Analysis 顾问)",
            role_ref="product-manager",
            authority_policy={
                "task.schedule": "allow",
                "planning.decide": "allow",
            },
        ),
        RoleSpec(
            name="Architect",
            department="Engineering",
            responsibility="架构决策与技术方案",
            role_ref="architect",
            authority_policy={"architecture.decide": "allow"},
        ),
        RoleSpec(
            name="Developer",
            department="Engineering",
            responsibility="技术实现",
            role_ref="developer",
            authority_policy={"code.modify": "allow"},
        ),
        RoleSpec(
            name="QA",
            department="Quality",
            responsibility="测试验证与评审 (执行权 != 审核权)",
            role_ref="tester",
            authority_policy={
                "test.execute": "allow",
                "review.approve": "allow",
            },
        ),
    ),
)


# ------------------------------------------------------------------ solo 模板
# 同一组织模型, 扁平: 无部门 (角色 company-level), 角色集同 software_company
# (CEO 存在 — Human; 一人兼 Founder/CEO/Operator + AI 部门员工)。

SOLO: CompanyTemplate = CompanyTemplate(
    template_id="solo",
    name="Solo AI Software Company",
    description=(
        "一人公司: Human = Founder/CEO/Operator (扁平, 无部门) + "
        "PM/Architect/Developer/QA AI 员工; 同一组织模型, 不允许两个系统"
    ),
    departments=(),
    roles=(
        RoleSpec(
            name="CEO",
            human=True,
            responsibility="最终批准权 (Human, 一人兼多职)",
            authority_policy={
                "company.manage": "allow",
                "employee.hire": "allow",
                "release.approve": "allow",
            },
        ),
        RoleSpec(
            name="Product Manager",
            responsibility="需求/计划/调度",
            role_ref="product-manager",
            authority_policy={
                "task.schedule": "allow",
                "planning.decide": "allow",
            },
        ),
        RoleSpec(
            name="Architect",
            responsibility="架构决策",
            role_ref="architect",
            authority_policy={"architecture.decide": "allow"},
        ),
        RoleSpec(
            name="Developer",
            responsibility="技术实现",
            role_ref="developer",
            authority_policy={"code.modify": "allow"},
        ),
        RoleSpec(
            name="QA",
            responsibility="测试验证与评审",
            role_ref="tester",
            authority_policy={
                "test.execute": "allow",
                "review.approve": "allow",
            },
        ),
    ),
)

# ------------------------------------------------------------------ content_company 模板（第二行业）
# ★ 2026-09-19 加（M6 · 补第二行业）—— 此前的模板只有 software_company / solo,
#   两个都是【软件行业】⇒ 无法证明"同一底座能承载别的行业"。本模板补上第一个非软件行业。
#   ★ 关键设计: 它**复用平台角色**（governor）与**通用工种**（writer / ui-designer）,
#     证明"平台角色 + 能力注册"确实能跨行业复用（而不是给每个行业另造一套）。

CONTENT_COMPANY: CompanyTemplate = CompanyTemplate(
    template_id="content_company",
    name="Content Studio (自媒体内容工厂)",
    description=(
        "自媒体内容工厂: Human CEO(终审) + 主编/作者/配图/运营 AI 员工; "
        "★ 复用平台角色 Governor 做合规与成本; Default Deny (发布权仅 CEO)"
    ),
    departments=("选题", "创作", "运营", "数据"),
    roles=(
        RoleSpec(
            name="CEO",
            department="选题",
            human=True,
            responsibility="内容方向与最终发布权 (Human, 唯一最终权)",
            authority_policy={
                "company.manage": "allow",
                "employee.hire": "allow",
                "content.publish": "allow",     # ★ 发布权仅 CEO（Default Deny 的落点）
            },
        ),
        RoleSpec(
            name="Editor-in-Chief",
            department="选题",
            responsibility="选题决策与稿件终审 (编 ≠ 写: 不亲自写稿)",
            role_ref="product-manager",         # 需求/计划/调度 —— 跨行业复用同一能力声明
            authority_policy={
                "topic.decide": "allow",
                "content.review": "allow",
            },
        ),
        RoleSpec(
            name="Writer",
            department="创作",
            responsibility="写稿 (★ 无发布权、无终审权 —— 职责分离靠 authority_policy 落地)",
            role_ref="writer",
            authority_policy={"content.draft": "allow"},
        ),
        RoleSpec(
            name="Visual Designer",
            department="创作",
            responsibility="配图与视觉 (复用通用视觉能力)",
            role_ref="ui-designer",
            authority_policy={"asset.create": "allow"},
        ),
        RoleSpec(
            name="Growth Operator",
            department="运营",
            responsibility="发布排期与渠道运营 (需 CEO 批准才能发)",
            role_ref="devops",                  # 运维语义跨行业复用
            authority_policy={"content.schedule": "allow"},
        ),
        RoleSpec(
            name="Governor",
            department="数据",
            responsibility="合规审查与成本控制 (★ 平台角色跨行业复用)",
            role_ref="governor",
            authority_policy={"audit.read": "allow", "gate.review": "allow"},
        ),
    ),
)


TEMPLATES: dict[str, CompanyTemplate] = {
    t.template_id: t for t in (SOFTWARE_COMPANY, SOLO, CONTENT_COMPANY)
}


def get_template(template_id: str) -> CompanyTemplate:
    """按 id 取模板; 未注册 → TemplateNotFoundError。"""
    template = TEMPLATES.get(template_id)
    if template is None:
        raise TemplateNotFoundError(f"unknown company template: {template_id!r}")
    return template


def list_templates() -> list[dict[str, Any]]:
    """模板清单 (CLI templates 读命令用, 只读)。"""
    return [
        {
            "template": t.template_id,
            "name": t.name,
            "description": t.description,
            "department_count": len(t.departments),
            "role_count": len(t.roles),
        }
        for t in TEMPLATES.values()
    ]


# ------------------------------------------------------------------ 角色体系统一 (S7-001)
# exec/roles.py 为单一角色事实源; 模板 RoleSpec.role_ref 引用其 role_id。
# 以下函数做覆盖审计 + 完整性校验 (org 模板 ↔ exec 注册表), 全部只读,
# 惰性 import exec.roles (Removal Isolation: 删除 factory-exec 不影响 Factory)。


def _load_exec_roles() -> Any:
    """惰性加载 exec/roles.py 注册表; 未安装 → None (Removal Isolation)。"""
    try:
        import importlib

        return importlib.import_module("ai_factory_os.plugins.agents.roles")
    except ImportError:
        return None


def template_role_coverage() -> dict[str, dict[str, Any]]:
    """模板角色 → exec 注册表覆盖审计 (双体系统一证明, S7-001)。

    返回 {template_id: {"total": N, "exec_refs": M, "human": K, "roles": [
    {name, role_ref, resolved, execution_kind, capabilities} ...]}}。
    exec 未安装 → resolved=False + reason="exec 未安装" (Removal Isolation,
    不假装覆盖)。
    """
    exec_roles = _load_exec_roles()
    out: dict[str, dict[str, Any]] = {}
    for tpl in TEMPLATES.values():
        rows: list[dict[str, Any]] = []
        for spec in tpl.roles:
            row: dict[str, Any] = {
                "name": spec.name,
                "role_ref": spec.role_ref,
                "human": spec.human,
            }
            if spec.human or not spec.role_ref:
                row["resolved"] = True  # Human/无执行角色: 无 exec 引用即合法
                row["execution_kind"] = "human" if spec.human else ""
                row["capabilities"] = []
            elif exec_roles is None:
                row["resolved"] = False
                row["reason"] = "exec 未安装"
            else:
                role = exec_roles.get_role(spec.role_ref)
                row["resolved"] = role is not None
                row["execution_kind"] = role.execution_kind if role else ""
                row["capabilities"] = list(role.capabilities) if role else []
            rows.append(row)
        out[tpl.template_id] = {
            "total": len(tpl.roles),
            "exec_refs": sum(1 for r in rows if r["role_ref"]),
            "human": sum(1 for r in rows if r["human"]),
            "roles": rows,
        }
    return out


def check_template_role_integrity() -> list[str]:
    """模板 role_ref → exec 注册表完整性校验 (全部解析成功 → [])。

    返回问题列表 (每条可读描述); 空 = 模板与单一注册表完全对齐
    (S7-001 验收: 零未解析引用)。exec 未安装 → 全部 role_ref 报缺失
    (Removal Isolation 下模板仍可实例化, 仅审计不可用)。
    """
    problems: list[str] = []
    exec_roles = _load_exec_roles()
    for tpl in TEMPLATES.values():
        for spec in tpl.roles:
            if spec.human or not spec.role_ref:
                continue
            if exec_roles is None:
                problems.append(
                    f"{tpl.template_id}:{spec.name} role_ref={spec.role_ref!r} "
                    f"未解析 (exec 未安装)"
                )
                continue
            if exec_roles.get_role(spec.role_ref) is None:
                problems.append(
                    f"{tpl.template_id}:{spec.name} role_ref={spec.role_ref!r} "
                    f"不在 exec 注册表"
                )
    return problems
