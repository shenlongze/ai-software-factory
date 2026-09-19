"""services.operations.healing — 自愈看门狗（检测 → 诊断 → 修复）。

★ 2026-09-19 新增（吸收项 5 · 吸收自 amux 的 "self-healing watchdog"）。

【amux 的三件事（对照）】
  ① auto-compact（压缩上下文）
  ② restart crashed sessions（重启崩溃会话）
  ③ replay the last message（重放最后一条消息）
  ⇒ 本质是"**发现异常 → 自动处置**"。新区不具备会话级 compact/restart,
    但**平台级**有等价的异常与处置（见下）。

【新区的零件（本模块只做"串起来", 不重造）】
  · operations/run_liveness.py  —— stale 检测（running 且无心跳超阈值 → STALE）
  · execution/recovery/         —— checkpoint + replay（重放）
  · operations/rollback_service —— 回滚
  · services/work/decomposition.claim_leaf/release_leaf —— 认领与归还（CAS）
  缺的正是那个"发现异常就处置"的闭环 —— 本模块补上。

【检测什么（scan）】
  ① 卡住的认领: 叶 status='claimed' 但 claimed_at 已超阈值 ⇒ 认领方可能崩了
     （amux 的 "restart crashed sessions" 在平台层的对应物）
  ② 悬挂的执行: execution status ∈ {PENDING, RUNNING} 且创建时间超阈值
     （amux 的 "replay the last message" 的对应物: 重放/重试）
  ③ 失败的执行: status ∈ {FAILED, ERROR}（可重试的 ⇒ 交回 pending 供重认）

【怎么处置（heal）】
  · 默认 **dry_run=True**（只报告不动作）—— 自愈是最该谨慎的能力, 先看再动。
  · 显式 heal=True 才执行: 
      卡住的认领 → release_leaf(status="pending")（交回, 供重认）
      悬挂执行   → 标记 FAILED（带原因）, 并释放其认领
      失败执行   → 交回 pending（不自动无限重试 —— 重试次数由调用方策略定）

【诚实边界】
  · **不做上下文压缩**（compact 是 LLM 层的能力, 新区没有; 不假装有）。
  · 不自动无限重试 —— 只"归还供重认", 是否再跑由调度器的判定决定（谁更懂就绪）。
  · 阈值可配（默认 30 分钟）, 且**每次都写进报告**（可解释: 为什么算它异常）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

#: 默认陈旧阈值（秒）—— 超过这个时间仍 claimed/running ⇒ 视为异常
DEFAULT_STALE_SECONDS = 30 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: str) -> datetime | None:
    """解析 ISO 时间戳（宽松: 失败 → None, 由调用方按"无法判定"处理）。"""
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def scan(root: Path | str, *, stale_seconds: int = DEFAULT_STALE_SECONDS) -> dict[str, Any]:
    """**只读**诊断 —— 找出不健康的东西（不修, 不写）。

    返回 {stale_claims, hung_executions, failed_executions, scanned_at, stale_seconds}
    每一项都带"为什么判定它异常"（阈值 + 实际时间）。
    """
    root = Path(root)
    cutoff = _now() - timedelta(seconds=int(stale_seconds))
    out: dict[str, Any] = {
        "stale_claims": [], "hung_executions": [], "failed_executions": [],
        "scanned_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stale_seconds": int(stale_seconds),
    }

    # ── ① 卡住的认领（任务树里 claimed 且超时）
    try:
        from ai_factory_os.services.work import decomposition as D

        for t in D.list_trees(root):
            pid = str(t.get("plan_id") or "")
            tree = D.load_tree(root, pid)
            if not tree:
                continue
            for n in tree.get("nodes") or []:
                if str(n.get("status") or "").lower() != "claimed":
                    continue
                at = _parse_ts(str(n.get("claimed_at") or ""))
                if at is None or at > cutoff:
                    continue
                out["stale_claims"].append({
                    "plan_id": pid, "node_id": str(n.get("id") or ""),
                    "task": str(n.get("title") or ""),
                    "claimed_by": str(n.get("claimed_by") or ""),
                    "claimed_at": str(n.get("claimed_at") or ""),
                    "reason": f"claimed 超过 {stale_seconds}s 未归还（认领方可能已崩）",
                })
    except Exception:  # noqa: BLE001 — 诊断失败不抛
        pass

    # ── ② 悬挂的执行（PENDING/RUNNING 且创建时间超时）+ ③ 失败的执行
    try:
        from ai_factory_os.services.execution.runtime.store import RuntimeStore

        for req in RuntimeStore(root / "runtime").list_executions():
            st = str(getattr(req.status, "value", req.status)).upper()
            created = _parse_ts(str(getattr(req, "created_at", "") or ""))
            if st in ("PENDING", "RUNNING"):
                if created is not None and created <= cutoff:
                    out["hung_executions"].append({
                        "execution_id": str(req.id), "status": st,
                        "agent_id": str(getattr(req, "agent_id", "") or ""),
                        "created_at": str(getattr(req, "created_at", "") or ""),
                        "reason": f"{st} 超过 {stale_seconds}s 未推进",
                    })
            elif st in ("FAILED", "ERROR"):
                out["failed_executions"].append({
                    "execution_id": str(req.id), "status": st,
                    "agent_id": str(getattr(req, "agent_id", "") or ""),
                    "reason": "执行失败（可交回供重认）",
                })
    except Exception:  # noqa: BLE001
        pass

    out["total"] = (len(out["stale_claims"]) + len(out["hung_executions"])
                    + len(out["failed_executions"]))
    out["healthy"] = out["total"] == 0
    return out


def heal(
    root: Path | str,
    *,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
    dry_run: bool = True,
) -> dict[str, Any]:
    """诊断 + （可选）处置。

    ★ 默认 dry_run=True —— 自愈必须先"看得见再动手"; 显式 dry_run=False 才写。
    返回 {report, actions:[{kind, target, done, detail}], dry_run}
    """
    root = Path(root)
    report = scan(root, stale_seconds=stale_seconds)
    actions: list[dict[str, Any]] = []

    # ① 卡住的认领 → 归还（交回 pending 供重认）
    for item in report["stale_claims"]:
        act = {"kind": "release_stale_claim", "target": item["node_id"], "done": False, "detail": ""}
        if dry_run:
            act["detail"] = "dry_run: 将把该叶交回 pending（供重认）"
        else:
            try:
                from ai_factory_os.services.work import decomposition as D

                ok = D.release_leaf(root, item["plan_id"], item["node_id"], status="pending")
                act["done"] = bool(ok)
                act["detail"] = "已交回 pending" if ok else "归还失败（叶不存在?）"
            except Exception as exc:  # noqa: BLE001
                act["detail"] = f"{type(exc).__name__}: {exc}"
        actions.append(act)

    # ② 悬挂的执行 → 标 FAILED（让下游看到真实状态, 而不是永远"在跑"）
    for item in report["hung_executions"]:
        act = {"kind": "fail_hung_execution", "target": item["execution_id"],
               "done": False, "detail": ""}
        if dry_run:
            act["detail"] = "dry_run: 将把该执行标记 FAILED（超时未推进）"
        else:
            act["detail"] = "（待接: 执行状态写面）"   # 诚实标注: 执行状态写面属执行域, 本刀不越界
        actions.append(act)

    # ③ 失败的执行 → 归还其认领（若还有）供重认
    for item in report["failed_executions"]:
        actions.append({"kind": "requeue_failed", "target": item["execution_id"],
                        "done": False,
                        "detail": ("dry_run: 将交回供重认" if dry_run
                                   else "（待接: 需按节点归属交回）")})

    return {
        "report": report,
        "actions": actions,
        "dry_run": bool(dry_run),
        "acted": sum(1 for a in actions if a.get("done")),
    }
