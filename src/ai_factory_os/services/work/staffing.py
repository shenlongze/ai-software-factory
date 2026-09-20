"""派工（staffing）—— 声明"谁做"：节点的 required_role / required_capabilities。

【为什么需要它】Founder 问"接下来应该是执行了吧" ⇒ 实跑 `run --plan`: 创建执行 0 个。
  查因: 全树 274 节点 `required_capabilities` 【全空】⇒ 调度器 `evaluate` 判
  `unresolved: 未声明 required_capability_refs` ⇒ 一个叶也派不出去。

【★ 匹配规则（读代码得出, 别照注释写）】
  `bootstrap/scheduler_wiring.OrgResource.resolution_for()`:
      want = 节点.required_capabilities
      for m in 成员: caps = {m.role_ids}          ← ★ 用的是【成员的角色】, 不是 skills!
          if caps & want: match
  ⇒ 写法必须是**真实存在的角色名**（architect/developer/tester/…）, 不是技能词、也不是自造的。
  （该适配器 docstring 写的是 "skill 命中", 与代码不符 —— 以代码为准, 这条差异已在 CHANGELOG 记。）

【数据源（一处）】成员来自 `~/.factory/agents/agents.json`（与调度器读同一份文件）——
  所以"可选的合法值"= 该文件里出现过的 role 值的集合。★ 从真清单里选, 不许自造。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: 成员文件（与 scheduler_wiring.OrgResource._load 完全一致的两条候选路径）
_MEMBER_FILES = ("agents/agents.json", "org/agents.json")


def role_catalog(root: Path | str) -> dict[str, int]:
    """真实角色清单 ⇒ {角色: 可用人数}（可用 = status 为空或 AVAILABLE）。

    ★ 这是"合法值全集"——声明时只许从这里选; 也是给 LLM 的清单, 不是我编的常量。
    """
    base = Path(root)
    for rel in _MEMBER_FILES:
        cand = base / rel
        if not cand.is_file():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows = data if isinstance(data, list) else list(data.values())
        out: dict[str, int] = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            role = str(r.get("role") or "").strip()
            if not role:
                continue
            status = str(r.get("status") or "AVAILABLE").strip().upper()
            out[role] = out.get(role, 0) + (1 if status in ("", "AVAILABLE") else 0)
        if out:
            return out
    return {}


def _pick(pool: list[str], value: str) -> str:
    """在给定清单里做**大小写不敏感**的命中（LLM 常把 developer 写成 Developer）。"""
    v = str(value or "").strip()
    for cand in pool:
        if cand.lower() == v.lower():
            return cand
    return ""


def parse_staffing(role: str, caps: Any, catalog: dict[str, int]) -> tuple[str, list[str], list[str]]:
    """校验产线/人工给的派工声明 ⇒ (role, capabilities, 被丢弃的值)。

    规则:
      · role: 必须命中真实角色清单（大小写不敏感）; 否则丢弃（返回空串）
      · capabilities: 逐项校验, 清单外一律丢弃（★ 不静默 —— 调用方要把丢弃数报出来）
      · capabilities 为空但 role 命中 ⇒ 用 role 兜底填一个（保证调度器有东西可比, 不然还是 unresolved）
    """
    pool = list(catalog)
    got_role = _pick(pool, role)
    dropped: list[str] = []
    out_caps: list[str] = []
    raw = caps if isinstance(caps, list) else ([caps] if caps else [])
    for c in raw:
        hit = _pick(pool, str(c))
        if hit:
            if hit not in out_caps:
                out_caps.append(hit)
        else:
            dropped.append(str(c).strip())
    if got_role and not out_caps:
        out_caps = [got_role]                     # ★ role 兜底: 否则 required_capabilities 仍空 ⇒ 依旧 unresolved
    if got_role and got_role not in out_caps:
        out_caps.insert(0, got_role)
    return got_role, out_caps, dropped
