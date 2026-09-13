"""factory-console/project_ssot.py — Project 数据真相 (SSOT) 对齐 (S34-P0-F3)。

原则: org/projects.json = 唯一可变真相 (name/status/stage/goal/description)。
      projects/{id}/project.json 的 name/status 是历史遗留缓存, 不得作为真相。

- ensure_org_truth: 扫描 projects/{id}/project.json 的漂移字段, 以 org 为准
  回写 project.json (缓存对齐) — 幂等, 不删除任何数据, 不断链。
- drift_report: 只读报告当前漂移 (审计用)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: project.json 里以 org 为准的字段 (缓存对齐, 禁止反向)
_ORG_AUTHORITATIVE = ("name", "status")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _write_json(path: Path, data: dict[str, Any]) -> bool:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:  # noqa: BLE001
        return False


def _org_map(root: Path) -> dict[str, dict[str, Any]]:
    org = _load_json(root / "org" / "projects.json")
    if not org:
        return {}
    projects = org.get("projects")
    if isinstance(projects, dict):
        return {str(k): (v if isinstance(v, dict) else {}) for k, v in projects.items()}
    return {}


def drift_report(root: str | Path) -> dict[str, Any]:
    """只读报告: 每项目 project.json 相对 org 的漂移字段。"""
    root = Path(root)
    org = _org_map(root)
    report: dict[str, Any] = {"checked": 0, "drifting": 0, "projects": []}
    for pid, org_proj in org.items():
        pj = _load_json(root / "projects" / pid / "project.json")
        if pj is None:
            continue
        report["checked"] += 1
        diffs = {}
        for field in _ORG_AUTHORITATIVE:
            org_val = org_proj.get(field)
            pj_val = pj.get(field)
            # 只有 org 有值且与 project.json 不同才算漂移 (org 缺失 → 不动)
            if org_val and pj_val and str(org_val) != str(pj_val):
                diffs[field] = {"org": org_val, "project_json": pj_val}
        if diffs:
            report["drifting"] += 1
            report["projects"].append({"project_id": pid, "diffs": diffs})
    return report


def ensure_org_truth(root: str | Path) -> dict[str, Any]:
    """以 org 为 SSOT 对齐 project.json 缓存 (幂等, 只回写漂移字段)。"""
    root = Path(root)
    org = _org_map(root)
    fixed = 0
    fixes: list[dict[str, Any]] = []
    for pid, org_proj in org.items():
        pj_path = root / "projects" / pid / "project.json"
        pj = _load_json(pj_path)
        if pj is None:
            continue
        changed = False
        for field in _ORG_AUTHORITATIVE:
            org_val = org_proj.get(field)
            pj_val = pj.get(field)
            if org_val and pj_val and str(org_val) != str(pj_val):
                pj[field] = org_val
                fixes.append({"project_id": pid, "field": field,
                              "from": pj_val, "to": org_val})
                changed = True
        if changed and _write_json(pj_path, pj):
            fixed += 1
    return {"fixed": fixed, "fixes": fixes[:50], "total_fixes": len(fixes)}
