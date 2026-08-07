"""factory-org/org/templates.py — company 模板 + Role 冲突规则。

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
    """模板中的角色定义 (department="" = company-level, Solo 扁平)。"""

    name: str
    department: str = ""
    responsibility: str = ""
    authority_policy: dict[str, str] = field(default_factory=dict)
    human: bool = False


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
            authority_policy={
                "task.schedule": "allow",
                "planning.decide": "allow",
            },
        ),
        RoleSpec(
            name="Architect",
            department="Engineering",
            responsibility="架构决策与技术方案",
            authority_policy={"architecture.decide": "allow"},
        ),
        RoleSpec(
            name="Developer",
            department="Engineering",
            responsibility="技术实现",
            authority_policy={"code.modify": "allow"},
        ),
        RoleSpec(
            name="QA",
            department="Quality",
            responsibility="测试验证与评审 (执行权 != 审核权)",
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
            authority_policy={
                "task.schedule": "allow",
                "planning.decide": "allow",
            },
        ),
        RoleSpec(
            name="Architect",
            responsibility="架构决策",
            authority_policy={"architecture.decide": "allow"},
        ),
        RoleSpec(
            name="Developer",
            responsibility="技术实现",
            authority_policy={"code.modify": "allow"},
        ),
        RoleSpec(
            name="QA",
            responsibility="测试验证与评审",
            authority_policy={
                "test.execute": "allow",
                "review.approve": "allow",
            },
        ),
    ),
)

TEMPLATES: dict[str, CompanyTemplate] = {
    t.template_id: t for t in (SOFTWARE_COMPANY, SOLO)
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
