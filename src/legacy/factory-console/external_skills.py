"""factory-console/external_skills.py — U-4 (v1.1.189): 外部 skill 真实加载执行。

Founder 2026-08-27: 外部 skill 在 agent 执行时真实注入指令 (不是 mock)。

- load_external_skills(skills_file, dirs): 扫描 <dir>/*/SKILL.md → 解析
  frontmatter (id/name/description/category/version) + 正文 (instructions)
  → 幂等写入 skills.json; 已存在 → 刷新 instructions/description, 不覆盖
  id/name。
- parse_skill_md(path): SKILL.md (Codex 风格 --- frontmatter --- + 正文) 解析;
  无 frontmatter → id=目录名, body 全为 instructions (诚实兜底)。
- 执行注入: skills.json 条目由 Service._get_skill_registry 一并注册进
  SkillRegistry → AgentExecutionLoop 解析 Agent 技能 → SkillContext.instructions
  进 planner prompt (真实注入, 非 mock)。

失败安全: 目录缺失/文件损坏 → 跳过 (不阻断); 写失败 → 静默。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def parse_skill_md(path: str | Path) -> dict[str, Any] | None:
    """解析 SKILL.md → {id, name, description, category, version, instructions}。

    Codex 风格: ---  frontmatter (key: value)  ---  正文 (instructions)。
    无 frontmatter → id=目录名, 正文全部为 instructions (诚实兜底)。
    无正文 → instructions 空 (Skill 仍注册, 执行时无注入 — 不编造指令)。
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    folder = p.parent.name or "external-skill"
    body = text.strip()
    meta: dict[str, str] = {}
    m = _FRONTMATTER_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip().lower()] = v.strip().strip('"').strip("'")
        body = m.group(2).strip()
    skill_id = meta.get("id") or folder
    return {
        "id": skill_id,
        "name": meta.get("name") or skill_id,
        "description": meta.get("description") or "",
        "category": meta.get("category") or "external",
        "version": meta.get("version") or "1.0.0",
        "instructions": body,
    }


def _load_skills(skills_file: str | Path) -> dict[str, Any]:
    try:
        d = json.loads(Path(skills_file).read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("skills"), dict):
            return d
        if isinstance(d, dict):
            return {"skills": d}
    except Exception:  # noqa: BLE001 — 缺失/损坏 → 空
        pass
    return {"skills": {}}


def _save_skills(skills_file: str | Path, data: dict[str, Any]) -> None:
    try:
        p = Path(skills_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:  # 写失败 → 静默 (加载尽力而为)
        pass


def load_external_skills(
    skills_file: str | Path,
    dirs: list[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """扫描 <dir>/*/SKILL.md → 幂等加载进 skills.json。返回本次加载/刷新条目。

    已存在 → 刷新 description/instructions/version (执行注入用正文);
    不覆盖 id/name/category (用户可改)。"""
    dirs = list(dirs or [])
    if not dirs:
        return []
    data = _load_skills(skills_file)
    skills = data["skills"]
    touched: list[dict[str, Any]] = []
    for d in dirs:
        base = Path(d)
        if not base.is_dir():
            continue
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            md = skill_dir / "SKILL.md"
            if not md.is_file():
                continue
            parsed = parse_skill_md(md)
            if parsed is None:
                continue
            sid = parsed["id"]
            existing = skills.get(sid)
            if existing is not None and isinstance(existing, dict):
                existing["description"] = parsed["description"] or existing.get("description", "")
                existing["instructions"] = parsed["instructions"]
                existing["version"] = parsed["version"]
                if not existing.get("category"):
                    existing["category"] = parsed["category"]
                touched.append(existing)
            else:
                record = {
                    "id": sid,
                    "name": parsed["name"],
                    "description": parsed["description"],
                    "category": parsed["category"],
                    "version": parsed["version"],
                    "instructions": parsed["instructions"],
                }
                skills[sid] = record
                touched.append(record)
    if touched:
        _save_skills(skills_file, data)
    return touched
