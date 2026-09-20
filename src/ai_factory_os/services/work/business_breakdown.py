"""需求拆解（业务模块拆分）—— Founder 说的"两层拆解"的【业务层】。

两层（Founder 明确）:
  ① 需求拆解（本模块）: 业务视角 —— 需求由哪些【业务模块】组成
        产出人话粒度: 「商品管理 / 订单 / 支付 / 用户中心」
  ② 任务拆解（decomposition）: 执行视角 —— 具体做哪些活、谁做、怎么验收
        产出专业粒度: 「编写 Prisma schema 与迁移」

★ 为什么必须分开: "普通人是看有可能不懂需求拆解的, 不懂架构设计的"（Founder 原话）
  ⇒ 业务层是给人看的（喂给"功能链路图"），执行层是给 agent 做的。

★ 与 LLM 的关系（实测教训）:
  deepseek-chat 单次输出上限 8192 tokens; 一次要太多模块必被截断（本仓踩过 25466 字符截断）。
  ⇒ 所以: 限制模块数（≤12）+ 每模块名字短（≤16 字）+ 功能点 ≤5 个 —— 输出体量可控。
  ⇒ 失败 ⇒ 响亮报错（不产半成品, 不假装成功）。
"""

from __future__ import annotations

import json
from typing import Any

_MAX_MODULES = 12      #: 模块数上限（防输出超限）
_MAX_NAME = 16         #: 模块名上限（业务名要短）
_MAX_FEATS = 5         #: 每模块功能点上限


def _prompt(prd_text: str) -> str:
    return (
        "你是产品经理。基于下面的 PRD, 把需求拆成【业务模块】—— 让**非技术的老板**一眼看懂"
        "这个产品由哪几块组成。\n"
        "要求:\n"
        f"· 最多 {_MAX_MODULES} 个模块, 每个模块名 ≤{_MAX_NAME} 字;\n"
        "· 用人的话, 不用技术词（要「商品管理」不要「catalog 服务」）;\n"
        f"· 每个模块给 ≤{_MAX_FEATS} 个功能点（也是人话）;\n"
        "· 模块间若有前后依赖, 在 depends_on 里写依赖的模块名（无则空数组）;\n"
        "· 只输出 JSON 数组, 不要解释、不要 markdown。格式:\n"
        '[{"name":"商品管理","features":["上架商品","分类"],"depends_on":[]}]\n'
        f"\nPRD:\n{prd_text[:6000]}\n"
    )


def _parse(content: str) -> list[dict[str, Any]] | None:
    """解析 LLM 输出为模块列表; 不合规 ⇒ None（不猜、不产半成品）。"""
    s = str(content or "").strip()
    if s.startswith("```"):
        s = "\n".join(ln for ln in s.splitlines() if not ln.strip().startswith("```")).strip()
    try:
        got = json.loads(s)
    except Exception:
        return None
    if not isinstance(got, list) or not got:
        return None
    out: list[dict[str, Any]] = []
    for it in got[:_MAX_MODULES]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()[:_MAX_NAME]
        if not name:
            continue
        out.append({
            "name": name,
            "features": [str(f).strip() for f in (it.get("features") or []) if str(f).strip()][:_MAX_FEATS],
            "depends_on": [str(d).strip() for d in (it.get("depends_on") or []) if str(d).strip()],
        })
    return out or None


def breakdown(prd_text: str, *, provider: Any) -> list[dict[str, Any]]:
    """把 PRD 拆成业务模块（人话粒度）。失败 ⇒ 抛错（不产半成品）。"""
    from ai_factory_os.infrastructure.llm.provider import ProviderRequest

    resp = provider.generate(ProviderRequest(task_context=_prompt(prd_text), max_tokens=2048))
    if not getattr(resp, "ok", False) or not (resp.content or "").strip():
        raise ValueError(f"需求拆解失败: {getattr(resp, 'error', '') or '空响应'}")
    mods = _parse(resp.content)
    if not mods:
        raise ValueError(
            "需求拆解输出不合规（不是 JSON 数组 / 结构不对）—— 不产半成品; "
            "可重试或检查 provider"
        )
    return mods
