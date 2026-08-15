"""factory-console/session/router.py — IntentRouter: intent_type → Action 声明式路由 (S10-048 P0)。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.4
- 映射表: intent_type → action_name (声明式 dict, 无 if/else 分派)
- register_route 注册/覆盖; route(intent, registry) 经 ActionRegistry.get 解析到 Action
- 未路由 (类型无映射 / 映射的 Action 未注册) → UnknownIntentError (明确, 不静默)
"""

from __future__ import annotations

from typing import Optional

from .action import Action, ActionRegistry
from .intent import IntentObject

#: 默认声明式映射 (intent_type → action_name; 3 个 P0 真实 Action + S10-049 agent.execute_task)
DEFAULT_ROUTES: dict[str, str] = {
    "create_project": "create_project",
    # S10-050 P3: 产品意图 → create_product action (ProductIntent → Project 桥接)
    "create_product": "create_product",
    "list_projects": "list_projects",
    "show_status": "show_status",
    # S10-049 P1: run_task → Agent Execution Kernel (execute_task action)
    "run_task": "agent.execute_task",
    # 别名: "execute_task" 意图直达 (显式任务执行语义, 同 action 名)
    "execute_task": "agent.execute_task",
    # S10-051 P4: 工程管线意图 → 规则生成 Action (PRD / 准备工程)
    "generate_prd": "generate_prd",
    "prepare_project": "prepare_project",
    # S10-052 P4: 执行编排意图 → Orchestrator Actions (执行项目 / 进度查询)
    "execute_project": "execute_project",
    "project_progress": "project_progress",
    # S10-053 P4: 质量修复意图 → RepairManager Action (修复失败任务)
    "repair_task": "repair_task",
    # S10-055 Task 005: 项目验收意图 → accept_project Action (USER_ACCEPTANCE → DELIVERED)
    "accept_project": "accept_project",
    # S10-055 Task 005/006: Workforce Intelligence 意图 → Workforce Actions
    # (查看团队 → 团队状态; 谁负责 → 最近任务 Agent; 为什么选择 → 计划 reason)
    "workforce": "workforce",
    "task_owner": "task_owner",
    "agent_reason": "agent_reason",
    # S10-056: Agent Team 意图 → Team Action (协作视图/创建团队;
    # workforce 映射保持不变 — 兼容既有 "查看团队" → 团队状态路径)
    "team": "team",
}


class UnknownIntentError(Exception):
    """未路由 Intent (类型无映射或映射 Action 未注册) — 调用方须明确提示, 不静默。"""


class IntentRouter:
    """Intent → Action 路由 (注册式, 无硬编码 if)。

    新增意图: register_route + ActionRegistry.register 各一行, 路由逻辑零改动。
    """

    def __init__(self, mapping: Optional[dict[str, str]] = None) -> None:
        self._mapping: dict[str, str] = dict(
            mapping if mapping is not None else DEFAULT_ROUTES
        )

    def register_route(self, intent_type: str, action_name: str) -> None:
        """注册/覆盖 intent_type → action_name 路由 (声明式映射)。"""
        if not intent_type or not action_name:
            raise ValueError("intent_type / action_name 不能为空")
        self._mapping[intent_type] = action_name

    def route(self, intent: IntentObject, registry: ActionRegistry) -> Action:
        """解析 Intent → Action 实例; 未路由 → UnknownIntentError (不静默)。

        两步解析: ① 映射表找 action_name (无映射 → 未配置路由);
        ② registry.get(action_name) (未注册 → 路由悬空, 明确报错)。
        """
        action_name = self._mapping.get(intent.intent_type)
        if action_name is None:
            raise UnknownIntentError(
                f"意图 {intent.intent_type!r} 未配置路由 "
                f"(可用: {', '.join(sorted(self._mapping))})"
            )
        action = registry.get(action_name)
        if action is None:
            raise UnknownIntentError(
                f"意图 {intent.intent_type!r} 路由到 Action {action_name!r} 但未注册"
            )
        return action

    def routes(self) -> dict[str, str]:
        """只读映射快照 (测试/审计)。"""
        return dict(self._mapping)
