"""services.work.steering — 运行中改向（Steering）。

★ 2026-09-19 新增（吸收项 7 · 吸收自 amux 的 "steering"）。

【amux 原文】
  "Steering: type into any running session from the dashboard or your phone —
   change direction mid-flight without stopping it."

【为什么需要】
  调度一旦启动, 现实会变: 需求改了 / 某叶不重要了 / 要停手。
  没有改向通道 ⇒ 只能"全停重来"（丢进度）或"眼睁睁看它跑完错的"。
  有改向 ⇒ **不改已完成的、只影响未做的**, 在飞行中转弯。

【设计（最小可用, 注入点 = 调度驱动的 tick 间隙）】
  ① 请求面: request(root, kind, target, reason, by) → append 到
     <root>/work/steering.jsonl（append-only ⇒ 可审计: 谁在何时要求改什么）
  ② 消费面: pending(root) 取未消费的; consume(root, ids) 标记已消费
  ③ 应用面（由调度驱动调用 apply_to_pump）:
       stop            → 停止继续推进（本轮之后不再 tick 新的批次）
       pause  <node>   → 该叶本轮起不再派发（从 ready 中剔除）
       resume <node>   → 解除 pause
       reprioritize    → 交给 rank（本模块只落指令, 排序由 core/scheduler 的 rank 做）
  ⇒ ★ 关键语义: **只影响未派发的**（已完成的叶不动 —— 改向不该回滚已完成的工作）。

【与"取消正在跑的执行"的区别（诚实边界）】
  · 本模块管的是"**调度层**的改向"（派谁、还派不派、优先级）。
  · 取消一个**已经在跑**的执行属于执行域（execution/kernel/runtime_session.cancel）——
    本模块**不越界**去停它, 只在报告里指出"该执行正在跑, 如需中断请走执行域的 cancel"。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 支持的改向种类（未知种类不拒绝, 但会被 apply 忽略 + 报告）
KINDS = ("stop", "pause", "resume", "reprioritize")


def _file(root: Path | str) -> Path:
    return Path(root) / "work" / "steering.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def request(
    root: Path | str,
    kind: str,
    *,
    target: str = "",
    reason: str = "",
    by: str = "",
    priority: int = 0,
) -> dict[str, Any]:
    """请求一次改向（append-only, 返回落库记录）。

    kind: stop | pause | resume | reprioritize
    target: 叶 id（stop 时留空 = 全体）
    by: 谁要求的（人/agent; 审计用 —— 改向必须有来源, 不来自"系统自己"）
    """
    rec = {
        "id": f"steer_{uuid.uuid4().hex[:10]}",
        "kind": str(kind),
        "target": str(target),
        "reason": str(reason),
        "by": str(by),
        "priority": int(priority or 0),
        "created_at": _now(),
        "consumed": False,
    }
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _all(root: Path | str) -> list[dict[str, Any]]:
    p = _file(root)
    if not p.is_file():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001 — 坏行跳过
                continue
    except Exception:  # noqa: BLE001
        return []
    return out


def pending(root: Path | str) -> list[dict[str, Any]]:
    """未消费的改向指令（newest-last）。"""
    return [r for r in _all(root) if not r.get("consumed")]


def consume(root: Path | str, ids: list[str]) -> int:
    """把指定指令标记为已消费（重写整个 jsonl —— 记录量小, 简单可靠）。"""
    p = _file(root)
    rows = _all(root)
    want = set(ids)
    n = 0
    for r in rows:
        if str(r.get("id")) in want and not r.get("consumed"):
            r["consumed"] = True
            r["consumed_at"] = _now()
            n += 1
    if n:
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                     encoding="utf-8")
    return n


def effective(root: Path | str) -> dict[str, Any]:
    """按顺序折叠全部指令 ⇒ 当前生效的改向状态。

    返回 {stop: bool, paused: {node_id: reason}, reprioritized: {node_id: prio}, applied:[ids]}
      · stop 一旦出现过就一直是 True（停止是终态, 不可被后续指令撤销 —— 要重启就重新驱动）
      · resume 会移除 paused 里的项（后写覆盖先写）
    """
    stop = False
    paused: dict[str, str] = {}
    reprio: dict[str, int] = {}
    applied: list[str] = []
    for r in _all(root):
        k = str(r.get("kind") or "")
        t = str(r.get("target") or "")
        applied.append(str(r.get("id") or ""))
        if k == "stop":
            stop = True
        elif k == "pause" and t:
            paused[t] = str(r.get("reason") or "")
        elif k == "resume" and t:
            paused.pop(t, None)
        elif k == "reprioritize" and t:
            reprio[t] = int(r.get("priority") or 0)
    return {"stop": stop, "paused": paused, "reprioritized": reprio, "applied": applied}
