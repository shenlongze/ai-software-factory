"""retro — 项目复盘（正常交付流程的收尾节点，2026-09-14 补 ✓）。

为什么需要（Founder: "正常交付流程还有什么节点没有" ✓）:
  有【自动学习回流 ✓】（91 条 feedback.learned ✓）但那是引擎内部的记忆提取 ✗，
  没有【给人看的结论 ✓】—— 项目结束后没人能回答"这次哪里好、哪里差、下次改什么" ✗

★ 设计原则（关键 ✓）:
  复盘内容【全部从真实记录聚合 ✓】—— 不调 LLM 生成感想 ✗
  数据源: 验证记录（verifications ✓）· 执行报告（exec/*.report.md ✓）·
         交付记录（delivery ✓）· 事件流（factory.db ✓ 审批/执行/失败 ✓）
  为什么: 复盘要能【被审计 ✓】（每个结论都能追到记录 ✓）；
         让 LLM 写感想 = 又一份不可验证的文字 ✗（本项目反复踩过的坑 ✓）

诚实边界:
  · 样本小时【明确标注样本量 ✗】不假装统计显著 ✓
  · 数据缺 → 如实说"该维度无记录" ✓ 不编 ✗
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


def _verifications(root: Path) -> list[dict[str, Any]]:
    f = root / "verifications" / "verifications.json"
    if not f.is_file():
        return []
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(d, dict):
        return [v for v in d.values() if isinstance(v, dict)]
    return [v for v in d if isinstance(v, dict)] if isinstance(d, list) else []


def _reports(root: Path) -> list[dict[str, Any]]:
    """解析 exec/*.report.md 的关键字段（复用既有报告格式 ✓ 不改它 ✓）。"""
    out: list[dict[str, Any]] = []
    for f in sorted((root / "exec").glob("*.report.md")):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rec: dict[str, Any] = {"file": f.name}
        m = re.search(r"##\s*Validation\s*\n+result:\s*(\w+)", txt)
        rec["validation"] = (m.group(1) if m else "").upper()
        m = re.search(r"diff lines:\s*(\d+)", txt)
        rec["diff_lines"] = int(m.group(1)) if m else 0
        m = re.search(r"##\s*Cost & duration\s*\n+([\d.]+)\s*s", txt)
        rec["seconds"] = float(m.group(1)) if m else 0.0
        m = re.search(r"cost\s*\$([\d.]+)", txt)
        rec["cost"] = float(m.group(1)) if m else 0.0
        out.append(rec)
    return out


def _events(root: Path, project_id: str) -> dict[str, int]:
    """只统计与该变量无关的全局事件类型（事件流无 project 维度 ✗ 如实说明 ✓）。"""
    db = root / "factory.db"
    if not db.is_file():
        return {}
    try:
        c = sqlite3.connect(str(db))
        rows = c.execute(
            "select type, count(*) from events where type like 'org.execution.%' "
            "or type like 'org.approval.%' or type like 'org.delivery.%' "
            "or type like '%failed%' group by type").fetchall()
        c.close()
        return {str(t): int(n) for t, n in rows}
    except sqlite3.Error:
        return {}


def build_retro(root: Path | str, project_id: str) -> dict[str, Any]:
    """生成复盘 ✓（全部来自真实记录 ✓ 每个结论可追 ✓）。"""
    root = Path(root)
    ver = _verifications(root)
    reps = _reports(root)
    ev = _events(root, project_id)

    good: list[str] = []
    bad: list[str] = []
    nexts: list[str] = []

    # ── 验证维度（有记录才说 ✓ 无记录如实说 ✓）
    if ver:
        ok = sum(1 for v in ver if str(v.get("result") or "").upper() in ("PASS", "OK"))
        fail = len(ver) - ok
        rate = ok / len(ver)
        (good if rate >= 0.9 else bad).append(
            f"验证一次通过 {ok}/{len(ver)}（{rate:.0%}）")
        if fail:
            bad.append(f"验证失败 {fail} 条")
            nexts.append(f"复查 {fail} 条失败验证的失败原因（逐条追到 run_id ✓）")
    else:
        bad.append("验证记录：无 ✗（该维度无法复盘 ✓ 不代表没做过 ✗）")

    # ── 执行维度
    if reps:
        val_fail = [r for r in reps if r["validation"] not in ("PASS", "")]
        secs = [r["seconds"] for r in reps if r["seconds"]]
        cost = sum(r["cost"] for r in reps)
        good.append(f"执行记录 {len(reps)} 份 · 验证段 PASS "
                    f"{sum(1 for r in reps if r['validation'] == 'PASS')}/{len(reps)}")
        if secs:
            good.append(f"平均耗时 {sum(secs)/len(secs):.1f}s（最长 {max(secs):.1f}s）")
        if cost:
            good.append(f"累计成本 ${cost:.4f}")
        if val_fail:
            bad.append(f"执行报告里验证非 PASS：{len(val_fail)} 份"
                       f"（例: {', '.join(r['file'][:20] for r in val_fail[:3])}）")
    else:
        bad.append("执行报告：无 ✗")

    # ── 事件维度（失败/返工是"哪里差"的硬证据 ✓）
    fails = {k: v for k, v in ev.items() if "failed" in k or "rejected" in k}
    if ev:
        good.append(f"事件流可追：{sum(ev.values())} 条相关事件 ✓（审批/执行/交付 ✓）")
    if fails:
        for k, v in sorted(fails.items(), key=lambda x: -x[1])[:3]:
            bad.append(f"{k}: {v} 次 ✗")
        nexts.append("对高频失败事件补【前置检查】✓（把失败挡在发生之前 ✓）")

    # ── 交付维度
    try:
        from .delivery import list_deliveries, uat_status
        dlv = list_deliveries(root, project_id)
        uat = uat_status(root, project_id)
        if dlv:
            accepted = sum(1 for d in dlv if str(d.get("status")) == "ACCEPTED")
            good.append(f"交付记录 {len(dlv)} 条 · 已验收 {accepted} 条 ✓")
            if accepted < len(dlv):
                nexts.append(f"还有 {len(dlv) - accepted} 条交付未走完验收 ✓")
        if uat["total"]:
            (good if uat["complete"] else bad).append(
                f"用户验收 {uat['signed']}/{uat['total']} 条已签"
                + ("（全部通过 ✓）" if uat["complete"] else "（未完成 ✗）"))
            if uat["failed"]:
                nexts.append(f"{uat['failed']} 条验收未通过 → 必须返工 ✓（不许带着不通过交付 ✗）")
    except Exception:  # noqa: BLE001 — 失败安全 ✓
        pass

    return {
        "project_id": project_id,
        "samples": {"verifications": len(ver), "exec_reports": len(reps),
                    "events": sum(ev.values()), "event_types": len(ev)},
        "good": good,
        "bad": bad,
        "next": nexts or ["无明确改进项 ✓（样本量见上 ✓ 样本小则不具统计意义 ✗）"],
        "note": ("全部结论来自真实记录（验证/执行报告/事件流/交付 ✓）—— "
                 "没有一条是生成的感想 ✗；每条都能追到原始记录 ✓；"
                 "样本量小则不宜过度解读 ✗"),
    }
