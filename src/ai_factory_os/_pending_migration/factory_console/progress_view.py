"""progress_view — 项目进度视图（2026-09-14，Founder: "监控，cli 中需要可以查看" ✓）。

为什么要有它（Founder 反复指出 ✓）:
  ① 我先做了个 home 目录脚本 ✗ —— 那不是产品入口 ✓（"有数据无入口=等于没有"✓）
  ② 它还依赖 /tmp/e2e_v3.log ✗ —— 我的测试脚本的日志 ✓ 不是产品数据 ✗
  → 本模块【只读产品自身的记录】✓ CLI 一条命令可看 ✓

数据源（全部是产品记录 ✓ 不依赖任何 /tmp ✓）:
  · 链路状态: 由【各域真实记录】推断
      会话（conversations ✓）→ 理解（understanding.facts ✓）→ PRD（product_truth/prds ✓）
      → 计划（product_truth/plans ✓）→ 执行（ProductionRun.node_runs ✓）
      → 交付（delivery/deliveries ✓）→ 验收（delivery/uat ✓）
  · 任务级: ProductionRun.node_runs + 树里的标题 + NodeRun.started/completed ✓
  · 执行器: 进程表里的外部 agent（codex/claude/hermes ✓）

诚实边界（不美化 ✓）:
  · 读不到的维度【如实标"—"✗】不编 ✗
  · 中文按显示宽度对齐 ✓（Founder 要求 ✓ 中文字宽算 2 ✓）
"""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


# ── 表格（中文对齐 ✓）────────────────────────────────────────────────
def _w(s: Any) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(s))


def _pad(s: Any, n: int, right: bool = False) -> str:
    s = str(s if s is not None else "")
    g = max(0, n - _w(s))
    return (" " * g + s) if right else (s + " " * g)


def table(rows: list[list[Any]], headers: list[str], right_cols: set[int] | None = None) -> str:
    right_cols = right_cols or set()
    cols = [max([_w(h)] + [_w(r[i]) for r in rows]) if rows else _w(h)
            for i, h in enumerate(headers)]
    sep = lambda a, b, c: a + b.join("─" * (x + 2) for x in cols) + c  # noqa: E731
    out = [sep("┌", "┬", "┐"),
           "│ " + " │ ".join(_pad(h, cols[i]) for i, h in enumerate(headers)) + " │",
           sep("├", "┼", "┤")]
    out += ["│ " + " │ ".join(_pad(r[i], cols[i], i in right_cols) for i in range(len(headers)))
            + " │" for r in rows]
    out.append(sep("└", "┴", "┘"))
    return "\n".join(out)


def _dur(sec: float) -> str:
    s = int(sec)
    return f"{s}s" if s < 60 else f"{s // 60}m{s % 60:02d}s"


def _agents_running() -> int:
    try:
        r = subprocess.run("pgrep -fc 'codex exec|claude -p|hermes -z'", shell=True,
                           capture_output=True, text=True, timeout=10)
        return int((r.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0


def _load_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _flat(d: Any) -> list[dict[str, Any]]:
    """兼容包装/扁平两格式 ✓（读侧必须兼容 ✓ 本会话踩过三次 ✗）。"""
    if isinstance(d, dict):
        inner = d.get("prds") or d.get("plans") or d.get("deliveries")
        d = inner if isinstance(inner, dict) else d
        return [v for v in d.values() if isinstance(v, dict)]
    return [v for v in d if isinstance(v, dict)] if isinstance(d, list) else []


def pick_project(root: Path, project_id: str = "") -> str:
    """显式指定 > 最近活跃（按目录 mtime ✓）。"""
    if project_id:
        return project_id
    ds = sorted((root / "projects").glob("project_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return ds[0].name if ds else ""


def build(root: Path | str, project_id: str = "") -> dict[str, Any]:
    """收集进度数据 ✓（只读 ✓ 不写任何东西 ✓）。"""
    root = Path(root)
    pid = pick_project(root, project_id)
    proj = root / "projects" / pid
    out: dict[str, Any] = {"project_id": pid, "chain": [], "tasks": [], "agents": _agents_running()}

    # 会话 / 理解
    convs = sorted((proj / "conversations").glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not convs:
        convs = sorted((root / "conversations").glob("*.json"), key=lambda p: p.stat().st_mtime)[-1:]
    facts = 0
    if convs:
        d = _load_json(convs[-1]) or {}
        u = d.get("understanding") or {}
        facts = len(u.get("facts") or [])
    out["chain"].append(["① 会话 + 理解", "✅" if convs else "⏳",
                         "human → system", f"{len(convs)} 个会话", f"{facts} 条事实"])

    # PRD / 计划
    prds = _flat(_load_json(proj / "product_truth" / "prds.json"))
    plans = _flat(_load_json(proj / "product_truth" / "plans.json"))
    out["chain"].append(["② PRD", "✅" if prds else "⏳", "product-manager",
                         f"{len(prds)} 份", ",".join(str(p.get("id"))[:12] for p in prds[:2])])
    out["chain"].append(["③ 计划", "✅" if plans else "⏳", "llm-拆解器",
                         f"{len(plans)} 份", ",".join(str(p.get("id"))[:12] for p in plans[:2])])

    # 执行（本项目的 run ✓）
    runs = []
    for f in sorted((root / "workflows" / "runs").glob("prun-*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        d = _load_json(f)
        if isinstance(d, dict) and (not pid or str(d.get("project_id") or "") == pid):
            runs.append(d)
    if runs:
        run = runs[0]
        nrs = run.get("node_runs") or []
        done = sum(1 for n in nrs if n.get("state") == "COMPLETED")
        st = str(run.get("state") or "")
        emoji = {"COMPLETED": "✅", "FAILED": "❌", "RUNNING": "🔄", "PENDING": "🔄"}.get(st, "🔄")
        out["chain"].append(["④ 真实执行", emoji, "codex" if out["agents"] else "—",
                             f"{done}/{len(nrs)}", st])
        titles = _titles(root, str(run.get("workflow_id") or ""))
        for n in nrs[-10:]:
            nid = str(n.get("node_id") or "")
            sec = ""
            rid = n.get("run_id")
            if rid:
                nd = _load_json(root / "nodes" / "runs" / f"{rid}.json")
                if isinstance(nd, dict) and nd.get("started_at") and nd.get("completed_at"):
                    try:
                        a = datetime.fromisoformat(str(nd["started_at"]).replace("Z", "+00:00"))
                        b = datetime.fromisoformat(str(nd["completed_at"]).replace("Z", "+00:00"))
                        sec = _dur((b - a).total_seconds())
                    except ValueError:
                        sec = ""
            out["tasks"].append([
                titles.get(nid, nid[-14:])[:30],
                {"COMPLETED": "✅ 完成", "FAILED": "❌ 失败", "BLOCKED": "⛔ 受阻",
                 "RUNNING": "🔄 进行中"}.get(str(n.get("state")), "🔄"),
                "codex" if rid else "—", sec or "—", "✓" if n.get("artifact_id") else ""])
    else:
        out["chain"].append(["④ 真实执行", "⏳", "—", "—", "—"])

    # 交付 / 验收
    ds = _flat(_load_json(proj / "delivery" / "deliveries.json"))
    uat = _load_json(proj / "delivery" / "uat.json") or {}
    items = uat.get("criteria") or []
    signed = [i for i in items if i.get("result")]
    out["chain"].append(["⑤ 交付", "✅" if ds else "⏳", "factory",
                         f"{len(ds)} 个", ",".join(str(d.get("status")) for d in ds[:2])])
    out["chain"].append(["⑥ 用户验收", "✅" if items and len(signed) == len(items) else
                         ("🔄" if signed else "⏳"), "Founder（人工 ✓）",
                         f"{len(signed)}/{len(items)}", ""])
    out["uat"] = {"total": len(items), "signed": len(signed)}
    return out


def _titles(root: Path, plan_id: str) -> dict[str, str]:
    """从树取节点标题 ✓（按 plan_id 精确匹配 ✓ 不用文件名猜 ✗）。"""
    out: dict[str, str] = {}
    if not plan_id:
        return out
    for f in sorted((root / "task_trees").glob("*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        d = _load_json(f)
        if isinstance(d, dict) and d.get("plan_id") == plan_id:
            for n in (d.get("nodes") or []):
                if isinstance(n, dict) and n.get("id"):
                    out[str(n["id"])] = str(n.get("title") or "")
            break
    return out


def render(root: Path | str, project_id: str = "") -> str:
    """渲染进度视图 ✓（UTF-8 无 emoji 兼容问题 ✓）。"""
    d = build(root, project_id)
    L = [f"📋 项目进度  {datetime.now():%H:%M:%S}   项目 {d['project_id'] or '(无)'}", ""]
    L.append(table([[c[0], c[1], c[2], c[3], c[4]] for c in d["chain"]],
                   ["链路步骤", "状态", "谁做的", "结果", "备注"]))
    L.append("")
    if d["tasks"]:
        L.append(f"📊 任务级（显示最近 {len(d['tasks'])} 条）")
        L.append(table(d["tasks"], ["任务", "状态", "执行者", "耗时", "产物"], right_cols={3}))
    else:
        L.append("📊 任务级：该项目暂无执行记录 ⏳")
    L.append("")
    L.append(f"⚙️  外部 agent: {'🔄 ' + str(d['agents']) + ' 个运行中' if d['agents'] else '⏹️  无'}")
    return "\n".join(L)
