"""产线声明: 模块 ↔ 数据实体（读/写）—— 让数据流程图上的线从【线索】变【实线】。

【为什么需要它】
  数据流程图（投影 C）的模块↔实体线有两个来源（见 data_flow.py 头部）:
    · evidence（线索）: 模块文案里**碰巧出现**实体名 ⇒ 覆盖 7/13, 还会漏（"商品管理"只匹到 Sku）
    · declared（声明）: 产线在拆解时**明确声明**本模块读/写哪些实体 ← 本模块负责产出它
  Founder 要的是"数据流程"成真 ⇒ 只有声明这条路是【系统记录的事实】。

【★ 不许编 —— 三条硬约束】
  ① 只许从【传入的实体清单】里选（清单来自项目真实数据模型, 由 data_flow.extract_entities 抽）
  ② 清单外的名字一律丢弃, 并**计数上报**（不静默吞）
  ③ 拿不准 ⇒ 返回空数组（宁可没有, 不要瞎标）
"""

from __future__ import annotations

import json
from typing import Any

from ai_factory_os.services.work.priority import VALID as VALID_PRIORITIES

_MAX_ENTS = 8          #: 一个模块最多声明几个实体（防一次倒一堆）


def _prompt(module: str, desc: str, acceptance: str, entities: list[str],
            roles: list[str] | None = None) -> str:
    staff = ""
    if roles:
        staff = (
            "· role 与 capabilities 只能从这份【真实角色清单】里选, 不许自己造:\n"
            f"    {', '.join(roles)}\n"
            "  （capabilities 可给 1~2 个: 主要是谁来做 + 需要哪些角色配合; role 是主责角色）;\n"
        )
    return (
        "你是资深技术负责人。下面是开发计划里的一个模块, 请判断它【读/写】哪些数据实体、"
        "给它一个【优先级】, 并指定【谁做】。\n"
        "★ 硬约束:\n"
        f"· 实体只能从这份清单里选, 不许出现清单外的名字: {', '.join(entities)}\n"
        f"· 最多选 {_MAX_ENTS} 个; 拿不准就返回空数组 []（宁可没有, 不要瞎标）;\n"
        "· access 只能是 read / write / both（只读查询=read, 建表或写入=write, 两者都=both）;\n"
        "· priority 只能是 P0 / P1 / P2 / P3: 越挡着别人做、越影响整体完工 ⇒ 越靠前（P0 最先）;"
        " 拿不准给 P2; 旁边支线给 P3;\n"
        f"{staff}"
        "· reason 一句话说清为什么（≤40 字）;\n"
        "· 只输出 JSON 对象, 不要解释、不要 markdown。格式:\n"
        '{"entities":[{"name":"Order","access":"write"}],"priority":"P1",'
        f'"role":"{roles[0] if roles else "developer"}","capabilities":["{roles[0] if roles else "developer"}"],'
        '"reason":"下单主流程，后面支付与对账都等它"}\n'
        f"\n模块: {module}\n"
        f"模块说明: {desc or '（无）'}\n"
        f"验收要求: {acceptance or '（无）'}\n"
    )


def _parse_full(content: str, allowed: set[str],
                roles: list[str] | None = None) -> dict[str, Any]:
    """解析 LLM 输出 ⇒ {entities, dropped, priority, reason, role, capabilities, staff_dropped}。

    · 实体: ★ 清单外的一律丢, 并计数（不静默）
    · 优先级: 只收 P0~P3（非法/缺失 ⇒ 空串, 由调用方决定不写 —— 不猜）
    · 派工: role/capabilities 只收【真实角色清单】里的值（清单外的丢弃并计数）
    容忍三种形态: 裸数组 / {"entities":[...]} / {"data_entities":[...]}
    """
    empty = {"entities": [], "dropped": 0, "priority": "", "reason": "",
             "role": "", "capabilities": [], "staff_dropped": []}
    s = str(content or "").strip()
    if s.startswith("```"):
        s = "\n".join(ln for ln in s.splitlines() if not ln.strip().startswith("```")).strip()
    try:
        got = json.loads(s)
    except Exception:  # noqa: BLE001 — 解析不了 ⇒ 当作"没声明", 由调用方决定重试
        return empty
    raw_priority, reason, raw_role, raw_caps = "", "", "", []
    if isinstance(got, dict):
        raw_priority = str(got.get("priority") or "").strip().upper()
        reason = str(got.get("reason") or "").strip()[:200]
        raw_role = str(got.get("role") or "").strip()
        caps = got.get("capabilities") or got.get("required_capabilities") or []
        raw_caps = caps if isinstance(caps, list) else [caps]
    items = (got.get("entities") or got.get("data_entities") or []) if isinstance(got, dict) else got
    if not isinstance(items, list):
        items = []

    out: list[dict[str, Any]] = []
    dropped = 0
    seen: set[str] = set()
    for it in items:
        name = str(it.get("name") if isinstance(it, dict) else it or "").strip()
        if not name:
            continue
        if name not in allowed:                     # ★ 清单外 = 编的 ⇒ 丢弃 + 计数
            dropped += 1
            continue
        if name in seen:
            continue
        seen.add(name)
        access = str((it.get("access") if isinstance(it, dict) else "") or "both").lower()
        out.append({"name": name, "access": access if access in ("read", "write", "both") else "both"})
        if len(out) >= _MAX_ENTS:
            break
    res = {**empty, "entities": out, "dropped": dropped,
           "priority": raw_priority if raw_priority in VALID_PRIORITIES else "",
           "reason": reason}
    if roles:
        from ai_factory_os.services.work import staffing as _st

        role, caps2, staff_dropped = _st.parse_staffing(raw_role, raw_caps, {r: 1 for r in roles})
        res.update({"role": role, "capabilities": caps2, "staff_dropped": staff_dropped})
    return res


def _parse(content: str, allowed: set[str]) -> tuple[list[dict[str, Any]], int]:
    """兼容旧签名（只关心实体）—— 判据仍只有 _parse_full 一份。"""
    r = _parse_full(content, allowed)
    return r["entities"], r["dropped"]


def parse_entity_spec(items: list[str], allowed: set[str]) -> list[dict[str, Any]]:
    """把人手写的声明("Order:write" / "User" / "Product:read")解析成 `data_entities`。

    写法: `名字[:access]`, access ∈ read|write|both（省略 = both; 也收 `名字=access`）。

    ★ 与 LLM 路径的差别（故意的）:
      · LLM 输出是【模型生成】⇒ 清单外的静默丢弃 + 计数上报（别因模型跑偏就报错中断整批）
      · 人输入是【明确指令】⇒ 清单外**当场抛错**（写错了要立刻纠正, 不能悄悄吞掉写库）
    """
    if not allowed:
        raise ValueError("没有实体清单 —— 项目里没有数据模型（*.prisma / *.sql）⇒ 不能声明")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        s = str(raw or "").strip()
        if not s:
            continue
        sep = ":" if ":" in s else ("=" if "=" in s else "")
        name, _, access = s.partition(sep) if sep else (s, "", "both")
        name, access = name.strip(), (access.strip().lower() or "both")
        if name not in allowed:
            near = sorted(allowed)[:6]
            raise ValueError(f"实体名不在项目的真实数据模型里: {name}（可选: {', '.join(near)} …）")
        if access not in ("read", "write", "both"):
            raise ValueError(f"access 只能是 read/write/both: {access!r}（写法如 {name}:read）")
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "access": access})
    if not out:
        raise ValueError("没解析出任何实体（写法如 --set Order:write User:read）")
    return out


def declare_module(                # noqa: N802 — 与 expand_module 同族命名
    module_title: str,
    *,
    desc: str = "",
    acceptance: str = "",
    entities: list[str],
    provider: Any,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    """让 LLM 为一个模块声明【实体 + 优先级 + 谁做】—— 一次调用三样产出（不额外烧 token）。

    返回 {entities, dropped, priority, reason, role, capabilities, staff_dropped}
    （priority/role 可能为空 = LLM 没给或给了清单外的值 ⇒ 不写, 不猜）。
    失败 ⇒ 抛错（不产半成品, 与 expand_module 同一纪律）。
    """
    from ai_factory_os.infrastructure.llm.provider import ProviderRequest

    if not entities:
        raise ValueError("没有实体清单 —— 项目里没有数据模型（*.prisma / *.sql）⇒ 不声明（不编）")
    role_list = list(roles or [])
    ctx = _prompt(module_title, desc, acceptance, list(entities), role_list)
    resp = provider.generate(ProviderRequest(task_context=ctx, max_tokens=1024))
    if not getattr(resp, "ok", False):
        raise ValueError(f"声明失败: {getattr(resp, 'error', '') or '调用失败'}")
    return _parse_full(resp.content, set(entities), role_list)
