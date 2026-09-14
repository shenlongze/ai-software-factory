"""project_show — 按项目 ID 查该项目【全部】信息（Founder 数据归属模型的兑现）。

模型（Founder 确认）:
  有 project_id → 属于项目 → 文件在 projects/<P-id>/ 下 ✓
  无 project_id → 公共 ✓
 ★ 推论: 物理位置本身就是索引 → "查项目全部信息" = 【读那个目录】✓
   （不跨 store 查询 ✓ 打包交付 = tar 该目录 ✓）

只读实现 ✓：不写任何数据，纯目录遍历 + 汇总。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

KIND_LABEL = {
    "ideas": "想法", "discoveries": "调研", "requirements": "需求",
    "prds": "PRD", "plans": "计划",
}


def _count_json(p: Path) -> int:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return len(d) if isinstance(d, (list, dict)) else 0
    except (OSError, ValueError):
        return 0


def collect_project(root: str | Path, project_id: str) -> dict[str, Any]:
    """读 projects/<P-id>/ 汇总该项目全部信息（读不到就返回空摘要 ✓ 不抛 ✗）。"""
    base = Path(root) / "projects" / project_id
    out: dict[str, Any] = {"project_id": project_id, "exists": base.is_dir(),
                           "sections": {}, "files": 0}
    if not out["exists"]:
        return out
    # 项目元数据（若在全局实体库，标注来源 ✓）
    meta = {}
    for cand in (base / "project.json", base / "meta.json"):
        if cand.is_file():
            try:
                meta = json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            break
    out["meta"] = meta

    # 会话
    convs = sorted(base.glob("conversations/conv-*.json"))
    out["sections"]["conversations"] = [f.stem for f in convs]
    # product_truth 各类
    pt: dict[str, int] = {}
    for f in sorted((base / "product_truth").glob("*.json")) if (base / "product_truth").is_dir() else []:
        n = _count_json(f)
        if n:
            pt[KIND_LABEL.get(f.stem, f.stem)] = n
    out["sections"]["product_truth"] = pt
    # 任务树
    trees = sorted(base.glob("tasks/PLAN-*.json"))
    out["sections"]["task_trees"] = [f.stem for f in trees]
    # 文档
    docs = sorted((base / "docs").glob("*")) if (base / "docs").is_dir() else []
    out["sections"]["docs"] = [f.name for f in docs if f.is_file()]
    # 沙箱
    ws = [f for f in (base / "workspace").rglob("*") if f.is_file()] if (base / "workspace").is_dir() else []
    out["sections"]["workspace"] = [str(f.relative_to(base / "workspace")) for f in ws[:12]]
    out["files"] = sum(1 for f in base.rglob("*") if f.is_file())
    return out


def render_project(root: str | Path, project_id: str) -> str:
    """人类可读的汇总（CLI 输出 ✓）。"""
    if not project_id:
        return "用法: factory projectos show <project_id>"
    d = collect_project(root, project_id)
    if not d["exists"]:
        return f"项目不存在: {project_id}\n（项目目录: projects/{project_id}/ 未找到 ✗）"
    meta = d.get("meta") or {}
    L = [f"=== 项目 {project_id} ==="]
    if meta:
        L.append(f"  标题: {meta.get('title') or meta.get('goal') or '(未记录)'}")
        L.append(f"  状态: {meta.get('status') or '?'}"
                 f" · 来源会话: {meta.get('source_conversation_id') or '-'}")
    else:
        L.append("  元数据: 未落在项目目录（实体库中 ✓ 后续刀迁入）")
    s = d["sections"]
    L.append("")
    L.append("── 归属明细（物理在 projects/<P-id>/ 下 ✓）")
    L.append(f"  会话      {len(s.get('conversations') or [])} 个"
             + (f" → {', '.join(s['conversations'][:3])}" if s.get("conversations") else ""))
    pt = s.get("product_truth") or {}
    L.append("  需求资产  " + (" · ".join(f"{k} {v}" for k, v in pt.items()) if pt else "(无)"))
    L.append(f"  任务树    {len(s.get('task_trees') or [])} 个"
             + (f" → {', '.join(s['task_trees'][:3])}" if s.get("task_trees") else ""))
    L.append(f"  文档      {len(s.get('docs') or [])} 份"
             + (f" → {', '.join(s['docs'][:4])}" if s.get("docs") else ""))
    L.append(f"  沙箱产出  {len(s.get('workspace') or [])} 个文件"
             + (f" → {', '.join(s['workspace'][:4])}" if s.get("workspace") else ""))
    L.append("")
    L.append(f"  目录共 {d['files']} 个文件 · 打包交付 = tar 该目录 ✓")
    return "\n".join(L)
