"""factory-runtime — Product Runtime 核心 (Phase 15A-1 + 裁决 B)。

独立 Extension 包 (phase15-runtime-design.md §1.1 + runtime-service-model.md):
不 import Core 内部。架构裁决 B (Core Command Model):
- Managed Services: Console 常驻 (uvicorn, 健康 = /api/dashboard);
  未来 Agent Worker / Scheduler 经 managed_services 注册。
- Command Execution: Core = factory CLI 短命令 (健康 = 命令可用性检查);
  Core 退出是预期, 非 crash。
安全边界 (§5): localhost binding + runtime token 文件 (600, 日志脱敏);
完整 API Authentication 属 Phase 18, 不修改 Console 实现。

导出: RuntimeManager (生命周期) / RuntimeError (域错误)。
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import RuntimeError
from .manager import RuntimeManager

__all__ = ["RuntimeManager", "RuntimeError"]
