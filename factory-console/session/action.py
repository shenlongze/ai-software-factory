"""factory-console/session/action.py — Action + ActionRegistry + ExecutionContext + ActionResult (S10-048 P0)。

Intent Execution Kernel 的执行单元: Intent 路由到 Action, Action 持有 handler
(调 Service Layer, 不复制业务), 经 ExecutionContext (workspace/session/user/
权限) 执行, 产出 ActionResult (结构化结果 → Renderer 展示)。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.3

组件:
- Action — 能力声明 (name/description/handler/permission/metadata)
- ActionRegistry — 注册表: register/get/list (注册式, 无硬编码 if)
- ExecutionContext — 执行上下文: workspace/session/user/project/intent + require()
- ActionResult — 结构化结果: ok/status/message/data/error (+ to_dict 渲染视图)

边界 (设计 §2.7):
- Action 只做薄调用 (Service Layer 在 cli_factory/org/exec), 不复制业务逻辑
- 权限: require("user") 基线全通过; project/admin RBAC 由后续 Task 强制
  (未实现复杂 RBAC — 不静默降级, 明确 PermissionError)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .context import SessionContext
from .intent import IntentObject

#: 结果状态常量 (ActionResult.status)
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


@dataclass
class Action:
    """能力声明 (注册式): name 唯一; handler 接收 ExecutionContext → ActionResult。

    permission: "user" | "project" | "admin" — 声明式权限元数据; 本 Phase
    仅强制 "user" 基线 (RBAC 权限模型由 S10-048 后续 Task 实现后启用)。
    """

    name: str
    description: str
    handler: Callable[["ExecutionContext"], "ActionResult"]
    permission: str = "user"
    metadata: dict[str, Any] = field(default_factory=dict)

    def execute(self, context: "ExecutionContext") -> "ActionResult":
        """执行 Action (设计 §2.1 数据流: Action.execute(context) → 调 Service Layer)。"""
        return self.handler(context)


class ActionRegistry:
    """Action 注册表: register / get / list (注册式 — 新增能力只需 register 一行)。"""

    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        """注册 Action (同名覆盖 — 显式声明式语义, 同 SlashCommandRegistry)。"""
        self._actions[action.name] = action

    def get(self, name: str) -> Optional[Action]:
        """按 name 取 Action; 未注册 → None (调用方决定提示, 不静默)。"""
        return self._actions.get(name)

    def list(self) -> list[Action]:
        """全部 Action, 按 name 排序 (list 稳定性)。"""
        return [self._actions[name] for name in sorted(self._actions)]


@dataclass
class ExecutionContext:
    """Action 执行上下文: workspace/session/user/project (+ 当前派发 intent)。

    intent: 当前派发的 IntentObject (handler 取参数); session 每次派发注入。
    """

    workspace: Path
    session: SessionContext
    user: str = "user"
    project: Optional[str] = None
    intent: Optional[IntentObject] = None

    def require(self, permission: str) -> None:
        """权限检查 (简单模型, S10-048 P0): "user" 基线权限全通过。

        未实现复杂 RBAC (设计 §2.3): project/admin 等更高权限不静默降级 —
        明确 PermissionError (由后续 Task 实现权限模型后启用 action.permission)。
        """
        if permission == "user":
            return
        raise PermissionError(
            f"权限不足: 需要 {permission!r} (当前仅实现 user 基线权限; "
            "RBAC 权限模型由 S10-048 后续 Task 实现)"
        )


@dataclass
class ActionResult:
    """Action 执行结果 (结构化 → Renderer 展示): ok/status/message/data/error。"""

    ok: bool = True
    status: str = STATUS_OK
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """渲染视图: 顶层契约字段 (ok/status/message/error) + data 键提升。

        data 键提升 → HumanRenderer 表格 (header/rows) 与键值展示直接可用
        (show_status 等状态类 Action 展示全部字段); 非 dict data → 保留 data 键。
        """
        view: dict[str, Any] = {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "error": self.error,
        }
        if isinstance(self.data, dict):
            view.update(self.data)
        else:
            view["data"] = self.data
        return view
