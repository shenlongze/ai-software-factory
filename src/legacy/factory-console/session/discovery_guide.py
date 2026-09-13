"""factory-console/session/discovery_guide.py — 产品发现引导体验共享模块 (S10-101 + S10-102)。

两路径 (conversation.py + discovery.py) 同步的唯一来源:
- LIFECYCLE_LINE / lifecycle_line — 生命周期引导文案 (发现→确认→创建→PRD→工程→开发,
  当前阶段用 [ ] 标出; 纯确定性, 不驱动状态机, 仅引导文案)
- format_progress — 必填字段进度 (产品定义 X/3 + 字段 ✅/待填; 纯状态计算,
  无 LLM 也显示)
- enhanced_line — DiscoverySession 增强字段可选提示 (使用场景/MVP范围/非功能要求,
  已填 ✅, 无待填则省略)
- HELP_KEYWORDS — 求助关键词确定性硬闸 (LLM 前先查, 两路径共用;
  normalize_help_text 去空白后子串匹配 — "没 想法" 等口语变体全覆盖)
- DEFAULT_SUGGESTIONS — 每字段确定性建议 (无 LLM 兜底 — 诚实降级, 非伪造 LLM)
- EXIT_COMMANDS — 退出命令集 (S10-103: 发现/确认两路径命令分流 — slash → 宿主
  passthrough; exit/quit/退出会话/再见/拜拜/结束 → exit_requested; "退出" 除外 —
  仍为取消发现, 向后兼容; session.EXIT_COMMANDS 同源导入)
- S10-102 确认阶段智能分流表 — APPROVE_WORDS / APPROVE_NEXT_ACTIONS /
  RENAME_RE / CLARIFY_WORDS / CONFIRM_DELEGATE_WORDS + 匹配助手
  (normalize_help_text / split_confirm_first / match_approve / match_approve_next /
  match_rename / match_clarify / match_delegate — conversation.handle_product_confirm
  确定性分流唯一来源)

设计: docs/sprint10/S10-101-discovery-guide-plan.md §1.1
边界:
- 纯标准库零依赖; 只读引用 session/product.FIELD_LABELS 与 REQUIRED_FIELDS
- 不改产品字段语义/状态机; 只提供展示/引导文案与求助兜底数据
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

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
    # S10-102: 求助词全覆盖 (口语/带空白变体 — normalize_help_text 去空白后命中)
    "随便", "你定", "你看吧", "你决定", "听你的", "都行", "都可以",
    "无所谓", "你推荐", "推荐个", "出个主意", "想不出来", "没想法了",
    "不知道做什么", "不知道做啥", "帮我拿主意", "都听你的", "怎么都行",
    # S10-118 (Founder 实测: "你把控一下"/"给我一点建议" 上下文断):
    # 把控系
    "把控", "你把握", "把一下关", "你来把关",
    # 建议系 (口语变体; "建议" 单独出现不触发 — 防误伤正常字段回答)
    "给我一点建议", "给我建议", "给建议", "提点建议", "建议一下",
    "给个方向", "你给个方向",
    # 委托系
    "你来想", "你想一个", "帮我想想", "你拿主意",
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


#: 退出命令集 (S10-103: 与 session.EXIT_COMMANDS 同源 — conversation 不能 import session,
#: 循环依赖; 单一来源: session.py 改为从此导入, 集合内容不变)
EXIT_COMMANDS: frozenset[str] = frozenset({"exit", "quit", "退出", "退出会话", "再见", "拜拜", "结束"})

# ================================================================ S10-102: 确认阶段智能分流表

#: 确认词 (纯确认 — 无下一步动作; 首段切分后小写匹配)
APPROVE_WORDS: tuple[str, ...] = (
    "y", "yes", "是", "确认", "同意", "可以", "好", "好的", "行",
    "行吧", "ok", "okay", "没问题", "就这样", "批准", "就这么办", "妥",
    "搞", "做", "上",
)

#: 确认+下一步 动作关键词 → action_id (首段确认词 + 剩余部分含关键词)
APPROVE_NEXT_ACTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prd", ("prd", "需求文档", "产品需求文档", "写需求", "出需求")),
    ("develop", ("开发", "开工", "开始做", "动工")),
    ("create", ("创建", "建项目", "创建项目")),
)

#: S10-104: next_action 动作直接短语 (正则, 无确认前缀 — "生成PRD"/"产出份prd文档"/
#: "出个html"/"出份功能清单"; 按 action_id 顺序返回首个命中; 纯动作请求 = 隐含确认+下一步)
DIRECT_ACTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prd",          (r"生成\s*prd", r"产出.*prd", r"出.*prd", r"写.*prd", r"prd")),
    ("feature_list", (r"功能清单", r"出.*清单", r"清单")),
    ("html",         (r"出.*html", r"生成.*html", r"做.*页面", r"html")),
    ("docs",         (r"文档", r"说明书", r"docs")),
)

#: 明确改名命令 (正则: 改名叫X / 名字改成X / 改名为X / 把名字改成X / 重命名为X / 名字改为X)
RENAME_RE = re.compile(r"(?:改名叫|名字改成|改名为|把名字改成|重命名为|名字改为)(.+)")

#: 澄清/问号请求 (→ 智能澄清, 不改名不确认)
CLARIFY_WORDS: tuple[str, ...] = (
    "?", "？", "为什么", "啥意思", "什么意思", "解释一下", "不明白",
    "没懂", "没明白", "这是什么", "然后呢", "啥", "怎么用", "能改吗",
)

#: 确认阶段委托词 (用户没想法交给你定 → 视为确认, 保持当前名称)
CONFIRM_DELEGATE_WORDS: tuple[str, ...] = (
    "随便", "你定", "你看吧", "你决定", "听你的", "你来定",
    "都行", "都可以", "无所谓", "你看着办", "都听你的", "怎么都行",
)

#: 确认输入首段切分 (按 ,。.!?空白 切 1 次 — 首段 + 剩余部分)
_CONFIRM_SPLIT_RE = re.compile(r"[，,。.、!?！？\s]+", re.UNICODE)


def normalize_help_text(text: str) -> str:
    """去全部空白 (半角/全角空格/tab/换行) — "没 想法"→"没想法"。

    求助词匹配前归一化: 口语变体 (带空格/全角空格) 与词表对齐。
    """
    return re.sub(r"\s+", "", str(text or ""))


def split_confirm_first(text: str) -> tuple[str, str]:
    """确认输入首段切分 → (首段小写, 剩余部分)。

    按 ,。.!?空白 切 1 次 — "可以，先出prd文档" → ("可以", "先出prd文档")。
    """
    norm = str(text or "").strip()
    parts = re.split(_CONFIRM_SPLIT_RE, norm, 1)
    first = parts[0].strip().lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""
    return first, rest


def match_approve(text: str) -> bool:
    """纯确认: 首段 ∈ APPROVE_WORDS ("可以"/"好"/"行"/y/yes → True)。"""
    first, _ = split_confirm_first(text)
    return first in APPROVE_WORDS


def match_approve_next(text: str) -> Optional[str]:
    """确认+下一步: 首段确认词 且 剩余含动作关键词 → action_id; 否则 None。

    "可以，先出prd文档" → "prd"; "好，开始开发" → "develop"; "行，创建项目" → "create"。
    """
    first, rest = split_confirm_first(text)
    if first not in APPROVE_WORDS:
        return None
    rest_lower = rest.lower()
    for action_id, keywords in APPROVE_NEXT_ACTIONS:
        if any(kw in rest_lower for kw in keywords):
            return action_id
    return None


def match_direct_action(norm: str) -> Optional[str]:
    """直接动作请求 → action_id (prd/feature_list/html/docs); 非动作请求 → None。

    大小写不敏感 (lower 后匹配); 按 DIRECT_ACTION_PATTERNS 顺序返回首个命中 —
    "产出份prd文档" → "prd"; "生成PRD" → "prd"; "出个html" → "html";
    "出份功能清单" → "feature_list"; "改名叫prd" → None (改名由 RENAME_RE 先处理)。
    """
    lowered = str(norm or "").lower()
    for action_id, patterns in DIRECT_ACTION_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return action_id
    return None


def match_rename(text: str) -> Optional[str]:
    """明确改名命令 → 新名称; 非改名命令 → None。

    "改名叫墨笺" → "墨笺"; "墨笺" (裸文本) → None (改名兜底由调用方处理)。
    """
    m = RENAME_RE.search(str(text or ""))
    if not m:
        return None
    return m.group(1).strip()


def match_clarify(text: str) -> bool:
    """澄清/问号请求: norm ∈ {"?","？"} 或含 CLARIFY_WORDS 词。

    "？" / "为什么" / "能改吗" → True (不改名不确认, 重展示摘要+解释选项)。
    """
    norm = str(text or "").strip()
    if norm in ("?", "？"):
        return True
    return any(kw in norm for kw in CLARIFY_WORDS)


def match_delegate(text: str) -> bool:
    """确认阶段委托: norm ∈ CONFIRM_DELEGATE_WORDS → True (视为确认, 不改名)。"""
    return str(text or "").strip() in CONFIRM_DELEGATE_WORDS


__all__ = [
    "LIFECYCLE_STAGES",
    "LIFECYCLE_LINE",
    "ENHANCED_LABELS",
    "EXIT_COMMANDS",
    "HELP_KEYWORDS",
    "DEFAULT_SUGGESTIONS",
    "APPROVE_WORDS",
    "APPROVE_NEXT_ACTIONS",
    "DIRECT_ACTION_PATTERNS",
    "RENAME_RE",
    "CLARIFY_WORDS",
    "CONFIRM_DELEGATE_WORDS",
    "normalize_help_text",
    "split_confirm_first",
    "match_approve",
    "match_approve_next",
    "match_direct_action",
    "match_rename",
    "match_clarify",
    "match_delegate",
    "lifecycle_line",
    "format_progress",
    "enhanced_line",
]
