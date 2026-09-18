"""services.conversation.binding — 会话 → 项目绑定（幂等）。

★ 2026-09-15 新增。功能来源: 老区 `canonical_golden_path.ensure_project_binding`
  （488 行 Orchestrator 里的一块）。**只借鉴做法, 不兼容老区** —— 老区整体要删。

【为什么需要它（Founder 指出）】
 会话/需求/文档/沙箱都该有【项目属性】；此前会话记录里连 project_id 字段都没有
 ⇒ 换个会话就找不到同一个项目的东西。
 ⇒ ④⑤⑥ 环全部基于"项目"概念（PRD/产物/任务树都挂在项目下）——
    所以绑定是链路的地基。

【做法（照老区已验证的逻辑, 一行不改语义）】
 1. 已有 project_id → 直接返回（**幂等**）
 2. 从 understanding 的 IDEA/REQUIREMENT 事实取 goal（前 80 字）
 3. 取不到 → 返回 ""（**还没理解出目标, 下次再说 —— 不猜**）
 4. 建 project 实体 + 落实体库 + 把 project_id 写回会话
 5. ★ 铁律: 属于项目的文件必须在项目目录下 ⇒ move_conv_to_project
 6. **失败安全**: 任何异常只打 stderr, 不阻断会话主链

【已避的坑（老区注释里记着的）】
 · 必须用 `_load_conv`（原始记录含 understanding）—— `get_conversation` 是过滤后的
   公开视图, 不含 facts（老区"第一版踩过"）。
 · 不走 `po.create_project(source_conv_id=…)` —— 它内部 extract_requirement 会把
   conv 当【实体】查, 而会话存在 conversations/ 不在实体库 ⇒ NOT_FOUND（老区实测踩到）。
   这里直接用实体 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

from ai_factory_os.contracts.entity.contract import create_entity
from ai_factory_os.infrastructure.storage.entity_store import store_entity
from ai_factory_os.services.conversation import understanding as pu

__all__ = ["ensure_project_binding"]

#: 目标事实的来源类型（IDEA 优先, REQUIREMENT 次之）
_GOAL_TYPES = ("IDEA", "REQUIREMENT")
#: 目标文本截断长度（老区取 80）
_GOAL_MAX = 80


def _goal_from_understanding(conv: dict) -> str:
    """从会话的 understanding 事实里取目标（IDEA/REQUIREMENT 的第一条）。"""
    und = conv.get("understanding") or {}
    facts = und.get("facts") if isinstance(und, dict) else {}
    seq = list(facts.values()) if isinstance(facts, dict) else list(facts or [])
    for want in _GOAL_TYPES:
        for f in seq:
            if isinstance(f, dict) and str(f.get("type", "")).upper() == want:
                goal = str(f.get("content") or "").strip()[:_GOAL_MAX]
                if goal:
                    return goal
    return ""


def ensure_project_binding(root: str | Path, conversation_id: str) -> str:
    """把会话绑到项目（幂等）: 有 project_id 直接返回；无则按理解出的目标建项目并回写。

    :returns: project_id；无法绑定（无理解结果 / 异常）→ ""（调用方不必特判）
    """
    try:
        conv = pu._load_conv(root, conversation_id)      # ★ 原始记录（含 understanding）
        if not conv:
            return ""
        pid = str(conv.get("project_id") or "")
        if pid:
            return pid

        goal = _goal_from_understanding(conv)
        if not goal:
            return ""                                     # 还没理解出目标 → 下次再说

        proj = create_entity("project", created_by="system", parent_id="")
        proj["title"] = goal
        proj["source_conversation_id"] = conversation_id
        proj["status"] = "ACTIVE"
        store_entity(root, proj)

        doc = pu._load_conv(root, conversation_id) or {}
        doc["project_id"] = str(proj.get("id") or "")
        pu._save_conv(root, conversation_id, doc)
        # ★ 铁律: 属于项目的文件必须在项目目录下
        pu.move_conv_to_project(root, conversation_id, str(doc["project_id"]))
        return str(doc["project_id"])
    except Exception as exc:  # noqa: BLE001 — 失败不阻断会话 ✓ 但必须可见
        print(f"[project] 会话→项目绑定失败: {exc}", file=sys.stderr)
        return ""
