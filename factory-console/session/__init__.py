"""factory-console/session — Workforce Terminal 交互会话包 (S10-047)。

设计: docs/sprint10/S10-047-session-design.md
纯标准库交互 shell (零依赖, 不接真实 LLM); 本包独立, 不侵入现有
cli_factory 命令逻辑 (main 只加一个分支)。

模块:
- session.py — InteractiveSession: 主循环 (banner/prompt/exit/quit/Ctrl+C/EOF)
- context.py — SessionContext + ContextManager: 会话上下文 (内存实现)
- (后续 Task: slash.py / commands.py / intent.py / renderer.py / completion.py)
"""

from .context import ContextManager, SessionContext
from .session import InteractiveSession

__all__ = ["InteractiveSession", "SessionContext", "ContextManager"]
