"""本工厂的角色与授权 —— 纯数据。

角色 = 能力集合 + 授权范围；角色不做事。
"""
from __future__ import annotations

from ai_factory_os.contracts.organization import Role

ROLES: tuple[Role, ...] = (
    Role(
        id="product-owner", name="产品负责人",
        capability_refs=("CAP-CONFIRM-PRD", "CAP-CONFIRM-PLAN", "CAP-DELIVER"),
        authority=("approve:prd", "approve:plan", "approve:delivery"),
    ),
    Role(
        id="engineer", name="工程师",
        capability_refs=("CAP-UNDERSTAND", "CAP-DRAFT-PRD", "CAP-DRAFT-PLAN",
                         "CAP-EXECUTE", "CAP-REPAIR"),
        authority=("write:workspace",),
    ),
    Role(
        id="reviewer", name="验收人",
        capability_refs=("CAP-VERIFY",),
        authority=("read:artifact", "write:evidence"),
    ),
)

ROLE_BY_ID: dict[str, Role] = {r.id: r for r in ROLES}
