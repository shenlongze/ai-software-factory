"""factory-console/session/skill_search.py — Skills 索引按需检索 (W5, v1.1.251).

抄 OpenClaw <available_skills>: 不把 147 个 skill 全量塞 system (省 token),
而是提供 skill_search 工具按需检索 (名字/关键词/分类) → 返回 {id, name, category, path};
模型需要专业技能时检索, 然后按需 read SKILL.md 加载指令 (Progressive Disclosure)。

skills.json 结构 (external_skills 写入): {skills: {id: {id,name,category,version,path?,description?}}}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: skills.json 位置 (与 external_skills.load_external_skills 一致)
def skills_file(root: str | Path) -> Path:
    return Path(root) / "skills" / "skills.json"


def list_skills(root: str | Path | None, query: str = "", top_k: int = 10) -> dict[str, Any]:
    """按名字/关键词/分类检索 skills。query 空 → 返回前 top_k (总览)。"""
    if not root:
        return {"ok": False, "error": "数据根为空", "skills": [], "total": 0}
    try:
        d = json.loads(skills_file(root).read_text(encoding="utf-8"))
        skills = d.get("skills") or {}
    except Exception as exc:  # noqa: BLE001 — 文件缺失/坏
        return {"ok": False, "error": f"skills 不可用: {exc}", "skills": [], "total": 0}
    items = []
    q = str(query or "").strip().lower()
    for sid, v in skills.items():
        name = str(v.get("name") or sid)
        cat = str(v.get("category") or "")
        desc = str(v.get("description") or "")
        if q:
            hay = f"{sid} {name} {cat} {desc}".lower()
            if q not in hay:
                continue
        items.append({"id": sid, "name": name, "category": cat,
                      "path": str(v.get("path") or "") or f"skills/{sid}/SKILL.md"})
    items = items[:top_k]
    total = len(skills)
    if not items:
        return {"ok": True, "output": f"技能库共 {total} 个, 无匹配『{query}』(可换关键词)", "skills": [], "total": total}
    out = f"技能库共 {total} 个, 匹配 {len(items)} 个:" + "\n" + "\n".join(
        f"- {s['name']} ({s['id']}) · 分类 {s['category']} · 路径 {s['path']}" for s in items
    )
    return {"ok": True, "output": out, "skills": items, "total": total}


def index_prompt(root: str | Path | None, max_items: int = 24) -> str:
    """system 注入的紧凑索引提示: 只列高频/通用 skill 名字 (OpenClaw <available_skills> 思路)。"""
    try:
        r = list_skills(root, top_k=max_items)
        if not r.get("ok"):
            return ""
        total = r.get("total") or 0
        names = [f"{s['name']}({s['id']})" for s in (r.get("skills") or [])]
        return (
            f"【可用技能】技能库共 {total} 个 (如 {'、'.join(names[:10])} 等)。"
            "需要专业技能时用 skill_search 检索具体技能, 再按其路径读取 SKILL.md 加载操作指引; "
            "不要假设技能内容, 按需加载。"
        )
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["list_skills", "index_prompt", "skills_file"]
