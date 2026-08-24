"""factory-console/session/discovery_guide.py — 产品发现引导体验共享模块 (S10-101)。

两路径 (conversation.py + discovery.py) 同步的唯一来源:
- LIFECYCLE_LINE / lifecycle_line — 生命周期引导文案 (发现→确认→创建→PRD→工程→开发,
  当前阶段用 [ ] 标出; 纯确定性, 不驱动状态机, 仅引导文案)
- format_progress — 必填字段进度 (产品定义 X/3 + 字段 ✅/待填; 纯状态计算,
  无 LLM 也显示)
- enhanced_line — DiscoverySession 增强字段可选提示 (使用场景/MVP范围/非功能要求,
  已填 ✅, 无待填则省略)
- HELP_KEYWORDS — 求助关键词确定性硬闸 (LLM 前先查, 两路径共用)
- DEFAULT_SUGGESTIONS — 每字段确定性建议 (无 LLM 兜底 — 诚实降级, 非伪造 LLM)

设计: docs/sprint10/S10-101-discovery-guide-plan.md §1.1
边界:
- 纯标准库零依赖; 只读引用 session/product.FIELD_LABELS 与 REQUIRED_FIELDS
- 不改产品字段语义/状态机; 只提供展示/引导文案与求助兜底数据
"""

from __future__ import annotations

from typing import Any, Iterable

from .product import FIELD_LABELS, REQUIRED_FIELDS

#: 生命周期阶段 (仅引导文案, 不驱动状态机 — 计划 §5 边界)
LIFECYCLE_STAGES: tuple[str, ...] = ("发现", "确认", "创建", "PRD", "工程", "开发")

#: 生命周期行 (无当前阶段标注的基础文案)
LIFECYCLE_LINE = "流程: " + "→".join(LIFECYCLE_STAGES)

#: 增强字段 → 中文名 (DiscoverySession 可选字段提示用)
ENHANCED_LABELS: dict[str, str] = {
    "usage_scenarios": "使用场景",
    "mvp_scope": "MVP范围",
    "non_functional_requirements": "非功能要求",
}

#: 求助关键词 (确定性硬闸 — LLM 前先查, 两路径共用; 命中才触发, 正常输入零影响)
HELP_KEYWORDS: tuple[str, ...] = (
    "给些建议", "给点建议", "给个建议", "给点意见", "给些意见",
    "没有想法", "没想法", "没思路", "没有思路", "你建议", "你看着办",
    "帮我出主意", "不知道怎么", "你帮我定", "你来定", "推荐一下",
    "有什么建议",
)

#: 每字段确定性建议 (无 LLM 兜底 — 诚实, 不伪造 LLM; 只覆盖字段追问面)
DEFAULT_SUGGESTIONS: dict[str, list[str]] = {
    "problem": ["现有工具太繁琐", "效率低/耗时长", "信息分散难管理"],
    "user": ["个人用户", "小团队/中小企业"],
    "core_features": ["快速录入", "分类统计", "导出报表"],
    "usage_scenarios": ["日常使用", "工作场景", "移动中随时用"],
    "mvp_scope": ["核心流程跑通", "单端先行"],
    "non_functional_requirements": ["数据安全", "响应快", "兼容主流设备"],
}


def lifecycle_line(current: str = "发现") -> str:
    """生命周期行: 当前阶段用 [ ] 标出, 并附 (当前: X)。

    例: lifecycle_line("确认") →
        "流程: 发现→[确认]→创建→PRD→工程→开发 (当前: 确认)"
    未知阶段 → 不加 [ ] 高亮, 仅附当前标注 (不抛)。
    """
    current = str(current or "").strip() or "发现"
    stages = list(LIFECYCLE_STAGES)
    if current in stages:
        stages[stages.index(current)] = f"[{current}]"
    return "流程: " + "→".join(stages) + f" (当前: {current})"


def format_progress(filled: Iterable[str], pending: Iterable[str]) -> str:
    """必填字段进度行: "产品定义 X/3: <字段>✅/待填 ..."。

    - filled: 已填字段名 (任意顺序, 只认必填 3 字段)
    - pending: 待填字段名 (任意顺序)
    - 字段中文名用 FIELD_LABELS (计划 §1.1: 必填 3 字段 problem/user/core_features)
    - 纯状态计算, 不依赖 LLM/analyzer — 无 key 也显示 (验收 3)
    """
    filled_set = set(str(f) for f in filled)
    pending_set = set(str(p) for p in pending)
    filled_count = 0
    parts: list[str] = []
    for field in REQUIRED_FIELDS:
        if field in filled_set and field not in pending_set:
            filled_count += 1
            parts.append(f"{FIELD_LABELS.get(field, field)}✅")
        else:
            parts.append(f"{FIELD_LABELS.get(field, field)}待填")
    return f"产品定义 {filled_count}/{len(REQUIRED_FIELDS)}: " + " ".join(parts)


def enhanced_line(answers: dict[str, Any]) -> str:
    """DiscoverySession 增强字段可选提示 (已填 ✅, 无待填则省略)。

    例: enhanced_line({}) →
        "增强(可选): 使用场景待填 · MVP范围待填 · 非功能要求待填"
    全部填齐 → "" (省略, 不刷屏)。
    """
    parts: list[str] = []
    pending_count = 0
    for field, label in ENHANCED_LABELS.items():
        value = (answers or {}).get(field)
        if value not in (None, "") and str(value).strip():
            parts.append(f"{label}✅")
        else:
            parts.append(f"{label}待填")
            pending_count += 1
    if pending_count == 0:
        return ""
    return "增强(可选): " + " · ".join(parts)


__all__ = [
    "LIFECYCLE_STAGES",
    "LIFECYCLE_LINE",
    "ENHANCED_LABELS",
    "HELP_KEYWORDS",
    "DEFAULT_SUGGESTIONS",
    "lifecycle_line",
    "format_progress",
    "enhanced_line",
]
