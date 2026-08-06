"""factory-runtime — Product Runtime 核心 (Phase 15A-1)。

独立 Extension 包 (phase15-runtime-design.md §1.1): 不 import Core 内部,
只通过子进程与 Core CLI / Console (uvicorn) 交互 (§1.2/§1.3 子进程隔离)。
安全边界 (§5): localhost binding + runtime token 文件 (600, 日志脱敏);
完整 API Authentication 属 Phase 18, 不修改 Console 实现。

导出: RuntimeManager (生命周期) / RuntimeError (域错误)。
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import RuntimeError
from .manager import RuntimeManager

__all__ = ["RuntimeManager", "RuntimeError"]
