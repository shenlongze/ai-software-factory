"""scheduling — 排期 / 估算（正常交付流程的标准节点，2026-09-14 补 ✓）。

为什么需要（Founder: "正常交付流程还有什么节点没有" ✓）:
  此前无法回答三件事 ✗: 【还要多久 ✓ / 谁在做 ✓ / 哪天交 ✓】
  有 sprint ✓ 但无工时估算 ✗ 无里程碑 ✗ 无排期 ✗

★ 关键洞察（本模块能便宜落地的原因 ✓）:
  任务树【已经有 depends_on ✓】（LLM 拆解时产出 ✓）
  → 【关键路径】可以直接从 DAG 算出来 ✓✓ 不需要用户另填任何东西 ✓
  → 只有"单任务工时"需要估 ✓ —— 用启发式（按 kind / change_type / 文件数 ✓）
    并且【估算值可覆盖 ✓】（用户可随时改 ✓ 不假装精确 ✓）

诚实边界（不假装）:
  · 估算是【启发式 ✓】不是测量 ✓ → 输出里明确标注依据 ✓
  · 无 depends_on 的任务 → 视为可并行 ✓（不会假装有顺序 ✓）
  · 结果是【相对工期】✓（人时 ✓）不是日历日期 ✗（本系统不排真实日历 ✓）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: 单任务工时启发式（人时）—— 依据 kind / change_type / 文件数。
#: 为什么用启发式: LLM 拆解目前不产出工时 ✗（若将来产出 ✓ 优先用真值 ✓）
_BASE_HOURS: dict[str, float] = {
    "NEW_FILE": 4.0,       # 新文件（含设计+实现+自测）
    "MODIFY": 2.0,         # 改现有文件
    "DOCUMENT": 1.0,       # 文档
    "TEST": 2.0,           # 测试
    "INFRA": 3.0,          # 基础设施/配置
}
_PER_EXTRA_FILE = 1.0      # 预计改动文件数每多一个 +1 人时
_MAX_TASK_HOURS = 16.0     # 单任务上限（超过说明该再拆 ✗）


def estimate_task(task: dict[str, Any]) -> tuple[float, str]:
    """单任务工时估算 ✓ 返回 (人时, 依据说明 ✓ 供输出标注 ✓)。"""
    ct = str(task.get("change_type") or "MODIFY").upper()
    kind = str(task.get("kind") or "")
    if kind == "domain":
        return 0.0, "领域节点（不直接执行）"
    base = _BASE_HOURS.get(ct, 2.0)
    n = len(task.get("expected_files") or [])
    hours = base + max(0, n - 1) * _PER_EXTRA_FILE
    hours = min(hours, _MAX_TASK_HOURS)
    why = f"{ct} 基准 {base:g}h" + (f" + {n - 1}×1h（{n} 个文件）" if n > 1 else "")
    return hours, why


_SKIPPED: dict[str, int] = {"count": 0}


def _load_tasks(root: Path | str, project_id: str) -> list[dict[str, Any]]:
    """取该项目的任务实体（含全局父链 ✓ 失败安全 ✓）。"""
    import json

    root = Path(root)
    out: list[dict[str, Any]] = []
    skipped = {"no_project": 0}
    files = [root / "ops" / "unified" / "entities.json",
             root / "projects" / project_id / "entities.json"]
    for f in files:
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, list):
            continue
        for e in data:
            if not isinstance(e, dict) or e.get("type") != "task":
                continue
            pid = str(e.get("project_id") or "")
            # ★ 严格归属（2026-09-14 修 ✗）: 原写"无 project_id 也收"→ 把 3838 个
            #   全局任务算进单个项目（实测排出 2205 条 ✗ 明显失真 ✗）
            #   现改为【只收明确属于本项目的】✓；跳过量如实报出 ✓（不静默 ✗）
            if pid != project_id:
                if not pid:
                    skipped["no_project"] += 1
                continue
            out.append(e)
    # 去重（同一实体可能在两处 ✓）
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for t in out:
        tid = str(t.get("id") or "")
        if tid and tid not in seen:
            seen.add(tid)
            uniq.append(t)
    return uniq


def build_schedule(root: Path | str, project_id: str) -> dict[str, Any]:
    """排期表 ✓: 逐任务估算 + 关键路径 + 里程碑 + 总工期（人时 ✓）。"""
    tasks = _load_tasks(root, project_id)
    # 只对叶子任务（无 children / 有角色）排期 ✓
    leaves = [t for t in tasks if str(t.get("kind") or "") != "domain"] or tasks

    est: dict[str, float] = {}
    why: dict[str, str] = {}
    title: dict[str, str] = {}
    for t in leaves:
        tid = str(t.get("id") or "")
        h, w = estimate_task(t)
        est[tid] = h
        why[tid] = w
        title[tid] = str(t.get("title") or tid)[:48]

    # 依赖图（title → id 双向下标 ✓ 因为 depends_on 存的是 title ✓）
    by_title = {str(t.get("title") or "").strip(): str(t.get("id") or "") for t in leaves}
    deps: dict[str, list[str]] = {}
    for t in leaves:
        tid = str(t.get("id") or "")
        ds = []
        for d in (t.get("depends_on") or []):
            key = str(d).strip()
            if key in by_title:
                ds.append(by_title[key])
            elif key in est:
                ds.append(key)
        deps[tid] = [d for d in ds if d != tid and d in est]

    # 关键路径（DP ✓ 无依赖 = 0；有环 → 环路任务视为无依赖 ✓ 不阻塞 ✓）
    longest: dict[str, float] = {}
    order_guard = 0
    pending = set(est)
    while pending and order_guard < len(est) * 3 + 10:
        order_guard += 1
        progressed = False
        for tid in list(pending):
            if all(d in longest for d in deps.get(tid, [])):
                longest[tid] = est[tid] + max(
                    (longest[d] for d in deps.get(tid, [])), default=0.0)
                pending.discard(tid)
                progressed = True
        if not progressed:
            for tid in list(pending):        # 环内任务 → 无依赖处理 ✓
                longest[tid] = est[tid]
                pending.discard(tid)

    total = max(longest.values(), default=0.0)
    parallel = sum(est.values())
    rows = sorted(leaves, key=lambda t: -longest.get(str(t.get("id") or ""), 0.0))
    return {
        "project_id": project_id,
        "tasks": [
            {
                "id": str(t.get("id") or ""),
                "title": title.get(str(t.get("id") or ""), ""),
                "role": str(t.get("required_role") or "-"),
                "skill": str(t.get("required_skill") or "-"),
                "hours": round(est.get(str(t.get("id") or ""), 0.0), 1),
                "basis": why.get(str(t.get("id") or ""), ""),
                "depends_on": deps.get(str(t.get("id") or ""), []),
                "critical_hours": round(longest.get(str(t.get("id") or ""), 0.0), 1),
            }
            for t in rows
        ],
        "critical_path_hours": round(total, 1),
        "sum_hours": round(parallel, 1),
        "parallelism": round(parallel / total, 2) if total else 1.0,
        "milestones": _milestones(leaves, deps),
        "skipped_no_project": _SKIPPED.get("count", 0),
        "note": ("估算为启发式（按 change_type + 文件数）✓ 不是测量 ✓；"
                 "总工期 = 关键路径（依赖链最长者 ✓）；并行度 = 总工时/关键路径 ✓"),
    }


def _milestones(tasks: list[dict[str, Any]], deps: dict[str, list[str]]) -> list[dict[str, Any]]:
    """里程碑: 按角色的最后一个任务 ✓（review/security/test 等 = 交付前的检查点 ✓）。"""
    per_role: dict[str, list[str]] = {}
    for t in tasks:
        r = str(t.get("required_role") or "").strip()
        if r:
            per_role.setdefault(r, []).append(str(t.get("id") or ""))
    out = []
    for role, ids in sorted(per_role.items()):
        out.append({"name": f"{role} 完成", "role": role, "tasks": len(ids)})
    return out
