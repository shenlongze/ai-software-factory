"""本工厂的能力声明 —— 纯数据。

每个能力必修 verify / effects / risk；approval 是能力属性，不是流程常量。
"""
from __future__ import annotations

from ai_factory_os.contracts.governance import ApprovalMode, ApprovalSpec
from ai_factory_os.contracts.resource import Capability, CostSpec

CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        id="CAP-UNDERSTAND", name="理解目标", satisfies="把自然语言目标结构化为需求",
        inputs=("conversation.goal",), outputs=("requirement",),
        verify="需求条目可回溯到会话原文", effects=(), risk="low",
        cost=CostSpec(tokens=20_000),
    ),
    Capability(
        id="CAP-DRAFT-PRD", name="起草方案", satisfies="产出可评审的方案",
        inputs=("requirement",), outputs=("prd",),
        verify="方案含目标/范围/验收标准三项",
        effects=(), risk="low", cost=CostSpec(tokens=40_000),
    ),
    Capability(
        id="CAP-CONFIRM-PRD", name="确认方案", satisfies="人对方案签字",
        inputs=("prd",), outputs=("approval",),
        verify="签字人身份在组织内且有权",
        effects=(), risk="low", cost=CostSpec(seconds=300),
    ),
    Capability(
        id="CAP-DRAFT-PLAN", name="起草计划", satisfies="把方案拆成可执行工作",
        inputs=("prd",), outputs=("plan",),
        verify="每个工作项有验收标准且依赖无环",
        effects=(), risk="low", cost=CostSpec(tokens=60_000),
    ),
    Capability(
        id="CAP-CONFIRM-PLAN", name="确认计划", satisfies="人对计划签字",
        inputs=("plan",), outputs=("approval",),
        verify="签字人身份在组织内且有权",
        effects=(), risk="low", cost=CostSpec(seconds=300),
    ),
    Capability(
        id="CAP-EXECUTE", name="执行生产", satisfies="按计划产出交付物",
        inputs=("plan",), outputs=("artifact",),
        verify="产物存在且可复现构建",
        effects=("write:workspace", "invoke:external"), risk="high",
        cost=CostSpec(tokens=200_000, money=1.0),
    ),
    Capability(
        id="CAP-VERIFY", name="验证结果", satisfies="独立判定产物是否达标",
        inputs=("artifact",), outputs=("verdict",),
        verify="验证过程与结论写入证据",
        effects=(), risk="low", cost=CostSpec(seconds=600),
    ),
    Capability(
        id="CAP-REPAIR", name="修复失败", satisfies="对未达标产物做修复",
        inputs=("verdict",), outputs=("artifact",),
        verify="修复后重新验证通过",
        effects=("write:workspace",), risk="high", cost=CostSpec(tokens=80_000),
    ),
    Capability(
        id="CAP-DELIVER", name="交付", satisfies="把产物移交使用方",
        inputs=("artifact",), outputs=("delivery",),
        verify="交付清单与验收标准逐条对齐",
        effects=("publish:external",), risk="high",
        approval=ApprovalSpec(mode=ApprovalMode.BEFORE, approver_role="product-owner"),
        cost=CostSpec(seconds=120),
    ),
)

CAPABILITY_BY_ID: dict[str, Capability] = {c.id: c for c in CAPABILITIES}
