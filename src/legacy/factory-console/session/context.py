"""factory-console/session/context.py — SessionContext + ContextManager (S10-047 Task 002)。

会话上下文 (内存实现, 不引入数据库): 会话 ID / 工作区 / 当前项目 / 当前
Agent / 元数据 / 历史。ContextManager 单会话持有, 进程退出即丢弃 (后续
Task 如需跨会话可接持久化, 非本 Sprint)。

用法:
    cm = ContextManager(workspace="/tmp/demo")
    cm.update(current_project="demo", current_agent="developer-1")
    cm.get().current_project  # "demo"
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from .product import ProductIntent

#: SessionContext 已知字段 (update 直接 setattr; 其余落入 metadata)
KNOWN_FIELDS = frozenset(
    {
        "session_id",
        "workspace",
        "current_project",
        "current_agent",
        "metadata",
        "history",
        "product_intent",  # S10-050 P5: 当前产品意图 (ProductIntent)
    }
)


class SessionContext:
    """单次交互会话的上下文对象 (可变, 由 ContextManager 读写)。"""

    def __init__(
        self,
        session_id: str | None = None,
        workspace: str | None = None,
    ) -> None:
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.workspace = workspace
        self.current_project: str | None = None
        self.current_agent: str | None = None
        self.metadata: dict[str, Any] = {}
        self.history: list[str] = []
        #: S10-050 P5: 当前产品意图 (ProductIntent | None — DISCOVERY 产物, create_product 消费)
        self.product_intent: Optional[ProductIntent] = None

    def to_dict(self) -> dict[str, Any]:
        """只读快照 (测试/后续 Renderer 展示用; 不暴露可变内部)。"""
        return {
            "session_id": self.session_id,
            "workspace": self.workspace,
            "current_project": self.current_project,
            "current_agent": self.current_agent,
            "metadata": dict(self.metadata),
            "history": list(self.history),
            "product_intent": (
                self.product_intent.to_dict() if self.product_intent is not None else None
            ),
        }


class ContextManager:
    """会话上下文管理器 (内存实现): get / update / record。"""

    def __init__(self, workspace: str | None = None) -> None:
        self.context = SessionContext(workspace=workspace)

    def get(self) -> SessionContext:
        """读取当前会话上下文 (同一对象, 内存单例)。"""
        return self.context

    def update(self, **kwargs: Any) -> SessionContext:
        """更新上下文: 已知字段 setattr; metadata 合并; 其余落入 metadata。

        context.current_project="demo" 风格: cm.update(current_project="demo")
        """
        for key, value in kwargs.items():
            if key == "metadata":
                self.context.metadata.update(value or {})
            elif key == "history":
                self.context.history.extend(value or [])
            elif key in KNOWN_FIELDS:
                setattr(self.context, key, value)
            else:
                self.context.metadata[key] = value
        return self.context

    def record(self, line: str) -> None:
        """记录一条会话输入到历史 (供后续 Task 上下文复用)。"""
        self.context.history.append(line)
