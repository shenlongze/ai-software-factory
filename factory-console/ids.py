"""factory_console/ids.py — 统一 ID 生成入口 (G7 Identity 收口)。

规则 (冻结, data-governance.md §1):
- 持久事实 ID = {domain_prefix}-{uuid hex}; 业务层禁止自行拼接 ID。
- 本入口收口 factory_console 域; org 数据空间用 org.models.new_id (同模式, 独立自洽)。
- 不改变已有持久 ID 格式 (向后兼容: 已落盘 ID 不变)。

用法: from factory_console.ids import new_id
"""

from __future__ import annotations

import uuid


def new_id(prefix: str, length: int = 10) -> str:
    """生成带域前缀的唯一 id (如 sess-1a2b3c4d5e)。默认 10 hex (与
    console_sessions 历史一致); org 层 8 hex 不影响唯一性。"""
    return f"{prefix}-{uuid.uuid4().hex[:length]}"
