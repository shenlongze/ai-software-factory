"""人话名翻译（display_name）—— 让用户视图真的"人话"。

背景（Founder 定的设计）:
  用户视图要给人看, 但专业层是"实现分类树、SPU/SKU 查询与详情…"这种 —— 普通人看不懂。
  ⇒ 所以人话层是【翻译】(Founder 选: "专业层更纯, 翻译不影响专业判断")。

现状与目标:
  · 现在 `_todo_display_name()` 用**规则派生**（去"模块 N: "前缀 + 切分句 + 限 24 字）
    ⇒ 快、稳、不花钱, 但**不真懂**（"编写 Prisma schema 与迁移"仍是专业话）。
  · 本模块用 LLM 翻译 ⇒ 写进节点的 `display_name` 字段（用户视图优先读它）。
  · ★ 字段优先于派生: 翻不好/没翻 ⇒ 视图自动回落规则派生（不会显示空白）。

★ 分批 + 限长（实测教训）:
  · deepseek-chat 单次输出上限 8192 tokens; 一次翻太多节点必被截断（本仓踩过:
    arch design 因输出 25466 字符被硬截断, 报错还误导成"字段缺失"）。
  · 所以: 每批 ≤10 个节点, 每个名字 ≤20 字, 并要求"只输出 JSON 数组"。
  · 某批失败 ⇒ 【不写那批】(保持规则派生), 报告里如实说 —— 不静默丢、不假装成功。
"""

from __future__ import annotations

import json
from typing import Any

_BATCH = 10          #: 每批节点数（防单次输出超限）
_MAX_NAME = 20       #: 每个名字上限（人话名要短）


def _prompt(items: list[tuple[str, str]]) -> str:
    """构造翻译 prompt。items = [(node_id, title)]。"""
    lines = "\n".join(f'{i+1}. {t}' for i, (_, t) in enumerate(items))
    return (
        "你是产品经理, 要把【技术任务标题】翻译成【普通人能看懂的一句话】。\n"
        "要求:\n"
        f"· 每条不超过 {_MAX_NAME} 个字, 说清「做什么事」, 不要技术黑话;\n"
        "· 保留业务含义（如「商品管理」而不是「catalog 模块」）;\n"
        "· ★ 必须输出【中文】—— 就算输入是英文模块名（如 project-scaffold、database）, "
        "也要译成中文（如「项目骨架」「数据库」）;\n"
        "· 不要编号、不要解释、不要 markdown;\n"
        '· 只输出 JSON 数组, 元素是字符串, 顺序与输入一一对应。例: ["搭建项目骨架","商品管理"]\n'
        f"\n输入 {len(items)} 条:\n{lines}\n"
    )


def _parse(content: str, n: int) -> list[str] | None:
    """从 LLM 输出里取 JSON 字符串数组; 数量不符 ⇒ None（不猜）。"""
    s = str(content or "").strip()
    # 剥可能的 markdown 围栏
    if s.startswith("```"):
        s = "\n".join(ln for ln in s.splitlines() if not ln.strip().startswith("```")).strip()
    try:
        got = json.loads(s)
    except Exception:
        return None
    if not isinstance(got, list) or len(got) != n:
        return None
    out = [str(x).strip()[:_MAX_NAME] for x in got]
    return out if all(out) else None


def translate_titles(
    titles: list[tuple[str, str]],
    *,
    provider: Any,
) -> dict[str, str]:
    """把 [(node_id, title)] 翻成 {node_id: 人话名}。

    失败的那一批【跳过】(不写), 由调用方如实报告 —— 不静默、不假装成功。
    """
    from ai_factory_os.infrastructure.llm.provider import ProviderRequest

    result: dict[str, str] = {}
    for i in range(0, len(titles), _BATCH):
        batch = titles[i:i + _BATCH]
        try:
            resp = provider.generate(
                ProviderRequest(task_context=_prompt(batch), max_tokens=1024)
            )
        except Exception:
            continue                     # 本批失败 ⇒ 跳过（保持规则派生）
        if not getattr(resp, "ok", False) or not (resp.content or "").strip():
            continue
        names = _parse(resp.content, len(batch))
        if not names:
            continue
        for (nid, _), nm in zip(batch, names):
            result[nid] = nm
    return result
