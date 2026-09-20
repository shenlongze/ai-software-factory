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

_MAX_ENTS = 8          #: 一个模块最多声明几个实体（防一次倒一堆）


def _prompt(module: str, desc: str, acceptance: str, entities: list[str]) -> str:
    return (
        "你是资深后端负责人。下面是一个开发模块, 请判断它【读/写】哪些数据实体。\n"
        "★ 硬约束:\n"
        f"· 只能从这份清单里选, 不许出现清单外的名字: {', '.join(entities)}\n"
        f"· 最多选 {_MAX_ENTS} 个; 拿不准就返回空数组 []（宁可没有, 不要瞎标）;\n"
        "· access 只能是 read / write / both（只读查询=read, 建表或写入=write, 两者都=both）;\n"
        "· 只输出 JSON 数组, 不要解释、不要 markdown。格式:\n"
        '[{"name":"Order","access":"write"},{"name":"User","access":"read"}]\n'
        f"\n模块: {module}\n"
        f"模块说明: {desc or '（无）'}\n"
        f"验收要求: {acceptance or '（无）'}\n"
    )


def _parse(content: str, allowed: set[str]) -> tuple[list[dict[str, Any]], int]:
    """解析 LLM 输出 ⇒ (声明的实体, 被丢弃的名字数)。★ 清单外的一律丢, 并计数。"""
    s = str(content or "").strip()
    if s.startswith("```"):
        s = "\n".join(ln for ln in s.splitlines() if not ln.strip().startswith("```")).strip()
    try:
        got = json.loads(s)
    except Exception:  # noqa: BLE001 — 解析不了 ⇒ 当作"没声明", 由调用方决定重试
        return [], 0
    if isinstance(got, dict):                       # 容忍 {"entities": [...]} 形态
        got = got.get("entities") or got.get("data_entities") or []
    if not isinstance(got, list):
        return [], 0

    out: list[dict[str, Any]] = []
    dropped = 0
    seen: set[str] = set()
    for it in got:
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
    return out, dropped


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


def declare_module_entities(       # noqa: N802 — 与 expand_module 同族命名
    module_title: str,
    *,
    desc: str = "",
    acceptance: str = "",
    entities: list[str],
    provider: Any,
) -> tuple[list[dict[str, Any]], int]:
    """让 LLM 为一个模块声明读/写的实体。返回 (声明, 被丢弃的名字数)。

    失败 ⇒ 抛错（不产半成品, 与 expand_module 同一纪律）。
    """
    from ai_factory_os.infrastructure.llm.provider import ProviderRequest

    if not entities:
        raise ValueError("没有实体清单 —— 项目里没有数据模型（*.prisma / *.sql）⇒ 不声明（不编）")
    ctx = _prompt(module_title, desc, acceptance, list(entities))
    resp = provider.generate(ProviderRequest(task_context=ctx, max_tokens=1024))
    if not getattr(resp, "ok", False):
        raise ValueError(f"声明失败: {getattr(resp, 'error', '') or '调用失败'}")
    return _parse(resp.content, set(entities))
