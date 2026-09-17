"""infrastructure/ids.py — 统一 ID 生成入口 (G7 Identity 收口)。

规则 (冻结, data-governance.md §1):
- 持久事实 ID = {domain_prefix}{sep}{uuid hex}; 业务层**禁止自行拼接 ID**。
- 本入口收口全仓; 各域若有历史格式（长度/分隔符不同）→ **传参保留**, 不擅自改格式
  （已落盘数据是混的: 8/10/12/16 位, `-` 与 `_` 两种分隔符都存在 ⇒ 统一格式会造新旧不一致）。
- 不改变已有持久 ID 格式 (向后兼容: 已落盘 ID 不变)。

用法:
    from ai_factory_os.infrastructure.ids import new_id
    new_id("ver")                 # ver-1a2b3c4d5e        （默认 10 位）
    new_id("EXR", 8)              # EXR-03ef8a71          （execution 域历史格式）
    new_id("conv", 12)            # conv-13cbd29e0774     （conversation 域历史格式）
    new_id("req", 16, "_")        # req_33846c95b001      （下划线分隔的历史格式）

★ 2026-09-15 收敛: 原先全仓有 10+ 处各自实现（organization/execution/governance/
  conversation/product_truth/decomposer/task_registry/os_core_identity …）,
  全部改为**委派本入口并传自己的历史参数**（实现收敛, 格式不变）。
"""

from __future__ import annotations

import uuid


def new_id(prefix: str, length: int = 10, sep: str = "-") -> str:
    """生成带域前缀的唯一 id（默认 10 hex, 与 console_sessions 历史一致）。

    :param prefix: 域前缀（如 ver / EXR / conv / PRD）
    :param length: hex 截取长度（各域历史不同, 默认 10）
    :param sep:    前缀与 hex 之间的分隔符（默认 "-"; 历史上有 "_"）
    """
    return f"{prefix}{sep}{uuid.uuid4().hex[:length]}"
