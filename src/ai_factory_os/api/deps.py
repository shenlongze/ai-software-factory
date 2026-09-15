"""api/deps.py — 全部域 router 共享的依赖（只放横切关注点 ✓）。

纪律: 这里只允许放**与域无关**的东西（数据根 / 鉴权 / 追踪上下文）。
      任何业务判断都不属于本文件 ✗（业务在 services/<域>/ ✓）。
"""
from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    """数据根 —— 与 CLI / 仓内其它组件同口径 ✓。

    优先级: FACTORY_DATA_DIR > DATA_DIR > ~/.factory
    （与 fastapi_adapter 的 DEFAULT_ROOT、CLI 的 --data-dir 默认值一致 ✓）
    """
    env = os.environ.get("FACTORY_DATA_DIR") or os.environ.get("DATA_DIR")
    return Path(env) if env else (Path.home() / ".factory")


# 待接线（不在本刀范围 ✗）:
#   trace_context —— 现有实现只在 _pending_migration/factory_console/ 里（老区 ✗），
#   而新层 API 禁 import 老区 ✗ ⇒ 等追踪上下文落进新层（infrastructure/events/）后再在此暴露 ✓
