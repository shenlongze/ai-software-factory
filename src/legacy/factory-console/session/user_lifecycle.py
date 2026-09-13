"""factory-console/session/user_lifecycle.py — UserLifecycle (S10-065 P1-1)。

统一用户视角生命周期 (GAP G4): 内部状态分散在 pipeline.Lifecycle /
orchestrator.ExecutionState (status/governance_status) / discovery.DiscoveryState —
本模块只做「映射层」: 内部状态 → 用户视角状态 (13 态), 不破坏内部 Lifecycle。

组件:
- UserLifecycle — 13 个用户视角状态常量 + STATUSES + map() + describe()
- DESCRIPTIONS — 每状态用户可读描述 (dict[str, str])

映射优先级 (确定性, 测试可精确断言 — 治理优先):
1. governance blocked / execution blocked (blocked/paused) → BLOCKED
2. waiting_for_review / review_required / pending_review → REVIEW
3. execution failed → FAILED
4. execution cancelled → CANCELLED
5. discovery 会话状态 (discovering/clarifying/... ) → DISCOVERY
6. 内部 Lifecycle → IDEA/PRODUCT_DEFINED/PLANNING/READY/PRODUCTION/VALIDATION/
   ACCEPTANCE/DELIVERED
7. 未知 → PRODUCTION (失败安全 — 不抛, 不静默假状态)

设计: docs/sprint10/S10-065-interactive-discovery-design.md §5
GAP: docs/sprint10/S10-065-gap-analysis.md G4
边界: 只读映射 (不修改 pipeline.Lifecycle / orchestrator / discovery 任何状态);
纯标准库零依赖; 输入宽容 (None/空/未知 → 失败安全)。
"""

from __future__ import annotations

from typing import Any, Optional

#: 发现会话内部状态 (DiscoveryState 值) — 用户视角统一归 DISCOVERY。
#: 注意: "cancelled" 是 discovery 终态, 但执行层 cancelled 同样归 CANCELLED,
#: 语义一致, 故不列入本表 (由 execution_status == "cancelled" 分支覆盖)。
_DISCOVERY_STATES: tuple[str, ...] = (
    "discovering",
    "clarifying",
    "ready_for_confirmation",
    "confirmed",
    "product_created",
)


class UserLifecycle:
    """用户视角生命周期 (映射层 — 不破坏内部 Lifecycle, 只做状态翻译)。

    13 态: IDEA → DISCOVERY → PRODUCT_DEFINED → PLANNING → READY →
    PRODUCTION → VALIDATION → REVIEW → ACCEPTANCE → DELIVERED,
    外加异常态 BLOCKED / FAILED / CANCELLED。
    """

    IDEA = "idea"
    DISCOVERY = "discovery"
    PRODUCT_DEFINED = "product_defined"
    PLANNING = "planning"
    READY = "ready"
    PRODUCTION = "production"
    VALIDATION = "validation"
    REVIEW = "review"
    ACCEPTANCE = "acceptance"
    DELIVERED = "delivered"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"

    #: 全部合法用户状态 (顺序 = 主路径推进方向 + 异常态)
    STATUSES: tuple[str, ...] = (
        IDEA,
        DISCOVERY,
        PRODUCT_DEFINED,
        PLANNING,
        READY,
        PRODUCTION,
        VALIDATION,
        REVIEW,
        ACCEPTANCE,
        DELIVERED,
        BLOCKED,
        FAILED,
        CANCELLED,
    )

    @classmethod
    def map(
        cls,
        internal_lifecycle: Optional[str],
        execution_status: Optional[str] = "",
        governance_status: Optional[str] = "",
        pending_review: bool = False,
    ) -> str:
        """内部状态 → 用户视角状态 (映射层, 治理优先, 失败安全)。

        参数:
        - internal_lifecycle — pipeline.Lifecycle 值 / discovery.DiscoveryState 值
          (execution_state.lifecycle / project.json status / discovery_sessions.json)
        - execution_status   — orchestrator ExecutionState.status
          (running/failed/delivered/blocked/paused/waiting_for_review/review_required/
           cancelled/replanning...)
        - governance_status  — ExecutionState.governance_status
          (blocked/waiting_for_review/review_required)
        - pending_review     — ReviewGate 存在 open 评审 (ProductionSession 聚合)

        返回: UserLifecycle 常量; 未知/空 → PRODUCTION (失败安全, 不抛)。
        """
        status = str(execution_status or "").strip().lower()
        gov = str(governance_status or "").strip().lower()
        lifecycle = str(internal_lifecycle or "").strip().lower()

        # ① 治理/执行阻塞 → BLOCKED (治理优先 — 阻塞压倒一切其它状态)
        if status in ("blocked", "paused") or gov == "blocked":
            return cls.BLOCKED
        # ② 等待人工评审 → REVIEW (评审优先于内部推进状态)
        if (
            status in ("waiting_for_review", "review_required")
            or gov in ("waiting_for_review", "review_required")
            or bool(pending_review)
        ):
            return cls.REVIEW
        # ③ 执行失败 → FAILED
        if status == "failed":
            return cls.FAILED
        # ④ 执行取消 → CANCELLED
        if status == "cancelled":
            return cls.CANCELLED
        # ⑤ 发现会话状态 (DISCOVERY 阶段) → DISCOVERY
        if lifecycle in _DISCOVERY_STATES:
            return cls.DISCOVERY
        # ⑥ 内部 Lifecycle 映射 (惰性 import — 与 production_session._map_phase 同模式)
        from .pipeline import Lifecycle

        if lifecycle == Lifecycle.IDEA:
            return cls.IDEA
        if lifecycle == Lifecycle.PRODUCT_DEFINED:
            return cls.PRODUCT_DEFINED
        if lifecycle == Lifecycle.ENGINEERING_READY:
            return cls.PLANNING
        if lifecycle == Lifecycle.EXECUTION_READY:
            return cls.READY
        if lifecycle == Lifecycle.DEVELOPMENT:
            return cls.PRODUCTION
        if lifecycle in (Lifecycle.TESTING, Lifecycle.VALIDATION_PASS):
            return cls.VALIDATION
        if lifecycle == Lifecycle.USER_ACCEPTANCE:
            return cls.ACCEPTANCE
        if lifecycle == Lifecycle.DELIVERED:
            return cls.DELIVERED
        # ⑦ 未知 → 失败安全 (不抛, 不返回伪造状态)
        return cls.PRODUCTION

    @classmethod
    def describe(cls, state: Optional[str]) -> str:
        """用户状态 → 用户可读描述 (未知 → 兜底提示, 不抛)。"""
        return DESCRIPTIONS.get(str(state or ""), "未知状态")


#: 每状态用户可读描述 (设计 §5 — "现在到哪了" 的可解释口径)
DESCRIPTIONS: dict[str, str] = {
    UserLifecycle.IDEA: "想法阶段 — 还没有开始探索需求",
    UserLifecycle.DISCOVERY: "需求探索中 — 正在收集产品需求",
    UserLifecycle.PRODUCT_DEFINED: "产品已定义 — 需求已确认, 等待进入工程",
    UserLifecycle.PLANNING: "规划中 — 正在生成工程计划与任务拆解",
    UserLifecycle.READY: "就绪 — 工程计划已就绪, 可以开始开发",
    UserLifecycle.PRODUCTION: "生产中 — AI 团队正在开发",
    UserLifecycle.VALIDATION: "验证中 — 正在测试与验证",
    UserLifecycle.REVIEW: "等待你确认 — 需要人工评审",
    UserLifecycle.ACCEPTANCE: "待验收 — 开发完成, 等待你确认交付",
    UserLifecycle.DELIVERED: "已交付",
    UserLifecycle.BLOCKED: "已阻塞 — 需要处理阻塞原因",
    UserLifecycle.FAILED: "失败 — 执行失败",
    UserLifecycle.CANCELLED: "已取消",
}

__all__ = [
    "UserLifecycle",
    "DESCRIPTIONS",
    "_DISCOVERY_STATES",
]
