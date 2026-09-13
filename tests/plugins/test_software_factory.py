"""plugins.factories.software —— 第一个工厂（纯数据）的一致性检查。"""
from __future__ import annotations

from pathlib import Path

from ai_factory_os.contracts.governance import ApprovalMode
from ai_factory_os.contracts.resource import ProviderType
from ai_factory_os.plugins.factories.software.acceptance import DELIVERY_ACCEPTANCE
from ai_factory_os.plugins.factories.software.bindings import BINDINGS
from ai_factory_os.plugins.factories.software.capabilities import CAPABILITIES, CAPABILITY_BY_ID
from ai_factory_os.plugins.factories.software.roles import ROLES
from ai_factory_os.plugins.factories.software.template import (
    CONDITIONAL_STEPS,
    CONDITIONAL_SUPPORTED,
    STEPS,
    instantiate,
)

CORE = Path(__file__).resolve().parents[2] / "src" / "ai_factory_os" / "core"


# ------------------------------------------------------------------ 能力声明

def test_capability_ids_are_unique_and_complete() -> None:
    ids = [c.id for c in CAPABILITIES]
    assert len(ids) == len(set(ids))
    for cap in CAPABILITIES:
        assert cap.verify, f"{cap.id} 缺 verify"
        assert cap.risk, f"{cap.id} 缺 risk"


# ------------------------------------------------------------------ 模板一致性

def test_every_step_capability_is_declared() -> None:
    for step in (*STEPS, *CONDITIONAL_STEPS):
        assert step.capability_ref in CAPABILITY_BY_ID, f"{step.key} → 未声明的能力"


def test_template_is_well_formed_and_acyclic() -> None:
    keys = [s.key for s in STEPS]
    assert len(keys) == len(set(keys))
    assert STEPS[0].depends_on == ()
    position = {s.key: i for i, s in enumerate(STEPS)}
    for step in STEPS:
        for dep in step.depends_on:
            assert dep in position, f"{step.key} → 悬空前驱 {dep}"
            assert position[dep] < position[step.key], f"{step.key} 成环"


# ------------------------------------------------------------------ 绑定与角色

def test_every_capability_has_at_least_one_binding() -> None:
    bound = {b.capability_id for b in BINDINGS}
    assert set(CAPABILITY_BY_ID) <= bound


def test_bindings_and_roles_reference_real_capabilities() -> None:
    for b in BINDINGS:
        assert b.capability_id in CAPABILITY_BY_ID
    for role in ROLES:
        for ref in role.capability_refs:
            assert ref in CAPABILITY_BY_ID, f"角色 {role.id} → 未声明的能力 {ref}"


# ------------------------------------------------------------------ 门是数据

def test_approval_is_data_driven_not_a_flow_constant() -> None:
    gated = {c.id for c in CAPABILITIES if c.approval.mode is not ApprovalMode.NONE}
    assert gated == {"CAP-DELIVER"}
    assert CAPABILITY_BY_ID["CAP-DELIVER"].approval.approver_role == "product-owner"


def test_the_two_gates_are_human_capabilities() -> None:
    for cap_id in ("CAP-CONFIRM-PRD", "CAP-CONFIRM-PLAN"):
        providers = {b.provider_type for b in BINDINGS if b.capability_id == cap_id}
        assert providers == {ProviderType.HUMAN}, cap_id


# ------------------------------------------------------------------ 验收标准

def test_delivery_acceptance_is_machine_checkable() -> None:
    assert DELIVERY_ACCEPTANCE
    for item in DELIVERY_ACCEPTANCE:
        assert item.statement and item.check, item.statement


# ------------------------------------------------------------------ 展开

def test_conditional_steps_are_declared_but_not_emitted() -> None:
    assert CONDITIONAL_STEPS and CONDITIONAL_SUPPORTED is False
    graph = instantiate(project_id="P-1", company_id="C-1", name="demo")
    assert all("step-repair" not in n.id for n in graph.nodes)


def test_instantiate_builds_a_consistent_graph() -> None:
    graph = instantiate(project_id="P-1", company_id="C-1", name="demo",
                        goal="做一个东西", deadline="2026-12-31T00:00:00Z")
    assert graph.project.acceptance == DELIVERY_ACCEPTANCE
    assert graph.work.project_id == graph.project.id
    assert graph.task.work_id == graph.work.id
    assert len(graph.nodes) == len(STEPS)

    ids = {n.id for n in graph.nodes}
    for node in graph.nodes:
        assert node.task_id == graph.task.id
        assert set(node.depends_on) <= ids, f"{node.id} 悬空前驱"
        assert node.required_capability_refs[0] in CAPABILITY_BY_ID
    assert graph.nodes[0].depends_on == ()


# ------------------------------------------------------------------ 边界

def test_core_knows_nothing_about_this_factory() -> None:
    source = "".join(p.read_text(encoding="utf-8") for p in sorted(CORE.rglob("*.py")))
    for cap in CAPABILITIES:
        assert cap.id not in source, f"内核出现能力 {cap.id}"
    for step in (*STEPS, *CONDITIONAL_STEPS):
        assert step.key not in source, f"内核出现步骤 {step.key}"
    for word in ("prd", "plan", "交付", "验证", "修复", "软件"):
        assert word not in source.lower(), f"内核出现业务词 {word}"
