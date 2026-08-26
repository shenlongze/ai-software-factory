"""factory-console/external_executor/host_assets.py — 宿主资产发现与导入 (M2)。

设计依据: 设计文档 §4.3 + Founder 2026-08-27 (标签/冲突/分组):
- 标签: source (⚡codex/🔶claude/🜲hermes) + kind (agent/skill/plugin/persona) + role (能力)
- 冲突: ID 命名空间隔离 (codex.<name> / claude.<name>); 幂等 (重复导入只刷新);
        手工同 ID → 跳过保留手工版
- 分组: 按 source / kind / role 三视图
- skills 复用 U-4 SKILL.md 解析; 注册时命名空间前缀 + source 元数据
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .asset_parsers import parse_asset_file
from .schema import ExternalExecutorAdapter, HostAssetsSpec

#: agent 名 → 能力角色 (路由用; 未命中 → assistant)
_ROLE_KEYWORDS: list[tuple[str, str]] = [
    ("architect", "architect"), ("architecture", "architect"),
    ("security", "security"), ("privacy", "security"),
    ("design", "designer"), ("ux", "designer"), ("polish", "designer"),
    ("review", "reviewer"), ("examiner", "reviewer"), ("audit", "reviewer"),
    ("test", "tester"), ("qa", "tester"),
    ("product", "product"), ("strategy", "product"), ("professor", "product"),
    ("research", "researcher"), ("analyst", "researcher"),
    ("developer", "developer"), ("engineer", "developer"), ("coding", "developer"),
    ("writer", "writer"), ("issue", "writer"), ("docs", "writer"),
    ("firebase", "backend"), ("backend", "backend"), ("frontend", "frontend"),
]


def derive_role(agent_id: str) -> str:
    """从 agent 名推导能力角色 (未命中 → assistant)。"""
    low = str(agent_id or "").lower()
    for kw, role in _ROLE_KEYWORDS:
        if kw in low:
            return role
    return "assistant"


def _load_json_map(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return d
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_json_map(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def scan_adapter_assets(adapter: ExternalExecutorAdapter) -> list[dict[str, Any]]:
    """按 adapter.host_assets 声明扫描 → 结构化资产 (只读, 未导入)。"""
    assets: list[dict[str, Any]] = []
    spec = adapter.host_assets
    if spec is None:
        return assets
    src = adapter.id
    home = Path.home()
    # ---- agents ----
    if spec.agents is not None:
        base = Path(str(spec.agents.dir).replace("~", str(home))).expanduser()
        if base.is_dir():
            for f in sorted(base.glob(spec.agents.glob or "*")):
                if not f.is_file():
                    continue
                parsed = parse_asset_file(f, spec.agents.format)
                if not parsed:
                    continue
                fields = spec.agents.fields or {}
                raw_name = str(parsed.get(fields.get("name", "name")) or f.stem).strip()
                if not raw_name:
                    raw_name = f.stem
                name = str(parsed.get(fields.get("name", "name")) or raw_name).strip()
                description = str(parsed.get(fields.get("description", "description")) or "").strip()
                prompt_field = fields.get("prompt", "prompt")
                prompt = str(parsed.get(prompt_field) or parsed.get("body") or "").strip()
                assets.append({
                    "id": f"{src}.{raw_name}",
                    "name": name or raw_name,
                    "description": description,
                    "prompt": prompt[:2000],
                    "source": src,
                    "kind": "agent",
                    "role": derive_role(raw_name),
                    "tags": [],
                    "host": {"cli": adapter.binary, "file": str(f)},
                })
    # ---- skills (复用 U-4 SKILL.md 解析; 注册时命名空间前缀) ----
    if spec.skills is not None:
        base = Path(str(spec.skills.dir).replace("~", str(home))).expanduser()
        if base.is_dir():
            for skill_dir in sorted(d for d in base.iterdir() if d.is_dir()):
                md = skill_dir / "SKILL.md"
                if not md.is_file():
                    continue
                # 复用 U-4 external_skills.parse_skill_md (路径级解析, 同款 frontmatter)
                from factory_console import external_skills as _ext_skills

                parsed = _ext_skills.parse_skill_md(md)
                if not parsed:
                    continue
                raw_id = str(parsed.get("id") or skill_dir.name).strip()
                assets.append({
                    "id": f"{src}.{raw_id}",
                    "name": str(parsed.get("name") or raw_id),
                    "description": str(parsed.get("description") or ""),
                    "instructions": str(parsed.get("instructions") or ""),
                    "source": src,
                    "kind": "skill",
                    "role": "",
                    "tags": [],
                    "host": {"cli": adapter.binary, "file": str(md)},
                })
    # ---- plugins (catalog: 只列目录) ----
    if spec.plugins is not None:
        base = Path(str(spec.plugins.dir).replace("~", str(home))).expanduser()
        if base.is_dir():
            for d in sorted(x for x in base.iterdir() if x.is_dir()):
                assets.append({
                    "id": f"{src}.plugin.{d.name}",
                    "name": d.name,
                    "description": "",
                    "source": src,
                    "kind": "plugin",
                    "role": "",
                    "tags": [],
                    "host": {"cli": adapter.binary, "file": str(d)},
                })
    # ---- persona (SOUL.md 等) ----
    if spec.persona is not None:
        p = Path(str(spec.persona.get("path") or "").replace("~", str(home))).expanduser()
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8")[:2000]
            except OSError:
                text = ""
            assets.append({
                "id": f"{src}.persona",
                "name": f"{adapter.name} 人格",
                "description": "宿主人格/系统提示 (SOUL.md)",
                "prompt": text,
                "source": src,
                "kind": "persona",
                "role": "",
                "tags": [],
                "host": {"cli": adapter.binary, "file": str(p)},
            })
    return assets


def import_assets(
    adapter: ExternalExecutorAdapter,
    assets: list[dict[str, Any]],
    *,
    agents_file: str | Path,
    skills_file: str | Path,
) -> dict[str, Any]:
    """导入资产 → AI 员工 (agents.json) + 技能 (skills.json)。

    规则 (Founder 确认):
    - agent → 员工注册表, 幂等 (同 ID 刷新 source/host, 保留用户 role/skills);
      手工同 ID → 跳过保留手工版 (skipped)
    - skill → skills.json, ID 命名空间前缀 (codex.<skill>), 幂等刷新 instructions;
      已有同 ID → 刷新不覆盖 name
    - plugin/persona → 只返回 catalog, 不注册 (不可执行)
    返回 {imported_agents, imported_skills, skipped, catalog}。
    """
    agents_data = _load_json_map(agents_file)
    agents_map = agents_data.get("agents") if isinstance(agents_data.get("agents"), dict) else {}
    if not isinstance(agents_map, dict):
        agents_map = {}
    skills_data = _load_json_map(skills_file)
    skills_map = skills_data.get("skills") if isinstance(skills_data.get("skills"), dict) else {}
    if not isinstance(skills_map, dict):
        skills_map = {}

    imported_agents: list[str] = []
    imported_skills: list[str] = []
    skipped: list[str] = []
    catalog: list[dict[str, Any]] = []

    for asset in assets:
        aid = str(asset.get("id") or "")
        kind = str(asset.get("kind") or "")
        if kind == "agent":
            if aid in agents_map:
                existing = agents_map[aid]
                # 手工注册 (无 source) → 保留手工版, 跳过
                if not isinstance(existing, dict) or not existing.get("source"):
                    skipped.append(aid)
                    continue
                # 幂等刷新: 保留用户 role/skills, 刷新 source 信息
                existing["source"] = str(asset.get("source") or "")
                existing["kind"] = "agent"
                existing["role"] = str(asset.get("role") or existing.get("role") or "assistant")
                existing["host"] = asset.get("host")
                existing["tags"] = asset.get("tags") or []
                if not existing.get("skills"):
                    existing["skills"] = []
                imported_agents.append(aid)
                continue
            agents_map[aid] = {
                "id": aid,
                "name": str(asset.get("name") or aid),
                "role": str(asset.get("role") or "assistant"),
                "skills": [],
                "source": str(asset.get("source") or ""),
                "kind": "agent",
                "description": str(asset.get("description") or "")[:300],
                "tags": asset.get("tags") or [],
                "host": asset.get("host"),
            }
            imported_agents.append(aid)
        elif kind == "skill":
            if aid in skills_map:
                existing = skills_map[aid]
                if isinstance(existing, dict):
                    existing["instructions"] = str(asset.get("instructions") or existing.get("instructions", ""))
                    existing["source"] = str(asset.get("source") or "")
                    existing["host"] = asset.get("host")
                    imported_skills.append(aid)
                    continue
            skills_map[aid] = {
                "id": aid,
                "name": str(asset.get("name") or aid),
                "description": str(asset.get("description") or ""),
                "category": "external",
                "version": "1.0.0",
                "instructions": str(asset.get("instructions") or ""),
                "source": str(asset.get("source") or ""),
                "host": asset.get("host"),
            }
            imported_skills.append(aid)
        else:
            catalog.append({k: asset.get(k) for k in ("id", "name", "kind", "source", "host")})

    agents_data["agents"] = agents_map
    skills_data["skills"] = skills_map
    _save_json_map(agents_file, agents_data)
    _save_json_map(skills_file, skills_data)
    return {
        "imported_agents": imported_agents,
        "imported_skills": imported_skills,
        "skipped": skipped,
        "catalog": catalog,
        "imported": len(imported_agents) + len(imported_skills),
    }
