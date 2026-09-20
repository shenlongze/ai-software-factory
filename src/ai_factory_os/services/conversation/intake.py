"""需求定位（intake locate）—— 需求进来的**第一件事**。

Founder 定的流程: 需求进来 → ① 定位 → ② 理解 → ③ 分析 → ④ 拆解
  "需求进来先定位" —— 定位不清, 后面每一步都"不知道站在哪"。

定位三要素:
  · 归属: 公司 / 部门 / 项目 —— 决定记忆存哪 · 权限谁能看 · 上下文带什么
  · 类型: 新项目 / 改现有 / 问答 / 一次性 —— 决定走哪条链
  · 承接: 谁提的（人）· 建议谁来分析（角色）—— ★ 决定④拆解的粒度（一个 agent 一次能做多少）

★ 判定用【规则 + 显示判据】（不是黑箱）:
  · 是为了"可解释、可纠正"—— 用户看到判据就能判断对不对, 不对可用 `--type` 覆盖。
  · 为什么不先用 LLM: 定位是流程第一步, 必须快且确定; LLM 判定可作为后续增强。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 需求类型（Founder 说的四类）
INTENT_TYPES: tuple[str, ...] = ("新项目", "改现有", "问答", "一次性")

#: 判定规则: (类型, 关键词模式, 说明) —— **按顺序匹配, 先命中先用**。
#: ★ 顺序有讲究: "改现有"比"新项目"优先 ——
#:   因为 "给现有系统加个登录" 同时含"加"与动词, 但它是改现有而不是新项目。
_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("改现有", ("改成", "改为", "修改", "优化", "重构", "修一下", "修下", "调整",
               "加上", "加个", "加一个", "新增", "去掉", "删除", "升级", "迁移"),
     "含改/加/删/优化类动词 ⇒ 是改现有"),
    ("问答", ("是什么", "为什么", "怎么", "如何", "能不能", "可以吗", "是否", "介绍",
             "解释", "有什么区别", "？", "?"),
     "含疑问词/疑问标号 ⇒ 是问答"),
    ("新项目", ("做一个", "做个", "开发一个", "开发个", "从零", "新建一个", "搭建一个",
               "实现一个", "写一个"),
     "含「做一个/开发/从零」等 ⇒ 是全新项目"),
)

#: 类型 → 建议承接角色（决定从哪一步开始、以及拆解粒度）
_SUGGEST_ROLE: dict[str, str] = {
    "新项目": "pm（产品经理: 先做需求分析 → 再架构 → 再拆解）",
    "改现有": "architect（架构师: 先看影响面 → 再改 → 再拆解）",
    "问答": "direct（直接回答, 不进流水线）",
    "一次性": "developer（开发: 直接做, 不用走完整链）",
}


@dataclass
class Location:
    """定位结果（三要素 + 判据）。"""

    project_id: str = ""
    department: str = ""
    company: str = ""
    intent: str = "未定"
    evidence: str = ""                      # ★ 判据（给用户看, 可判断对不对）
    proposer: str = ""                      # 谁提的
    suggested_role: str = ""                # 建议承接角色
    missing: list[str] = field(default_factory=list)   # ★ 还缺什么（要问用户的）

    def to_dict(self) -> dict[str, Any]:
        return {
            "归属": {"project": self.project_id, "department": self.department,
                     "company": self.company},
            "类型": self.intent,
            "判据": self.evidence,
            "承接": {"提出者": self.proposer, "建议角色": self.suggested_role},
            "还缺": self.missing,
        }


def locate(
    text: str,
    *,
    project_id: str = "",
    department: str = "",
    company: str = "",
    proposer: str = "",
    intent: str = "",
) -> Location:
    """定位一个需求 —— 返回三要素 + 判据 + 还缺什么。

    `intent` 显式给 ⇒ 不判定（用户说了算 —— 与 decompose"不猜"同一原则:
    猜不准就别猜, 让输入方给）。
    """
    loc = Location(
        project_id=project_id, department=department, company=company,
        proposer=proposer,
    )
    body = str(text or "").strip()

    if intent and intent in INTENT_TYPES:
        loc.intent = intent
        loc.evidence = "用户显式指定（不判定）"
    else:
        for name, kws, why in _RULES:
            hit = next((k for k in kws if k in body), "")
            if hit:
                loc.intent = name
                loc.evidence = f"{why}（命中: {hit!r}）"
                break
        else:
            loc.intent = "未定"
            loc.evidence = "没有命中任何规则 ⇒ 需要用户明确（不猜）"

    loc.suggested_role = _SUGGEST_ROLE.get(loc.intent, "")

    # ★ 还缺什么 —— 定位的目的是"缺什么就问什么"（不确认很可能做错）
    if not loc.project_id and loc.intent in ("新项目", "改现有"):
        loc.missing.append("归属: 属于哪个项目（改现有必须有; 新项目可先建）")
    if loc.intent == "未定":
        loc.missing.append("类型: 是新项目 / 改现有 / 问答 / 一次性")
    if not loc.proposer:
        loc.missing.append("承接: 谁提的")
    return loc
