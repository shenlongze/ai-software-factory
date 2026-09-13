"""交付验收标准 —— 纯数据。

每条必须机器可判（check 非空），否则不算标准。
"""
from __future__ import annotations

from ai_factory_os.contracts.work import Acceptance

DELIVERY_ACCEPTANCE: tuple[Acceptance, ...] = (
    Acceptance(statement="方案中的每条验收标准都有对应证据", check="evidence.covers(prd.acceptance)"),
    Acceptance(statement="验证结论为通过", check="verdict.status == 'accepted'"),
    Acceptance(statement="交付物清单完整", check="delivery.items == artifact.expected"),
    Acceptance(statement="全部动作可在审计链中回溯", check="audit.chain_intact()"),
)
