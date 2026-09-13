"""factory-console/session/progress_card.py — Durable 进度卡 (P0-B, v1.1.244).

抄 OpenClaw progress_card (原 update_plan) 思路: 计划/执行进度持久化为
"可查询的卡片", 不是 prompt 里的一句话 — 跨轮次、跨会话可查可展示。

结构 (<data_dir>/session_progress/<session_id>.json):
{
  "goal": str, "status": "idle|planning|running|done|blocked",
  "acceptance": [str], "tasks": [{"title","priority","status","backlog_id","verify"}],
  "created_at", "updated_at", "summary"
}

- save_from_plan(session_id, plan): plan_development 出计划 → 落卡 (planning)
- sync_from_exec(session_id, exec_state): 执行链推进 → 同步卡 (running/done)
- text(): 渲染成注入/查询用文本
失败安全: 文件坏/缺失 → 诚实空。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_STATUS = ("idle", "planning", "running", "done", "blocked")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def card_path(data_dir: str | Path, session_id: str) -> Path:
    return Path(data_dir) / "session_progress" / f"{session_id}.json"


def load_card(data_dir: str | Path | None, session_id: str) -> dict[str, Any]:
    """读进度卡; 无/坏 → 空卡 (失败安全)。"""
    if not data_dir or not session_id:
        return {}
    return _load_json(card_path(data_dir, session_id))


def save_from_plan(data_dir: str | Path | None, session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """plan_development 出计划 → 落卡 (planning 态)。"""
    card = {
        "goal": str(plan.get("goal") or "")[:120],
        "status": "planning",
        "acceptance": [str(a)[:200] for a in (plan.get("acceptance") or [])],
        "tasks": [{"title": str(t.get("title") or "")[:80],
                   "priority": str(t.get("priority") or "P2"),
                   "status": "todo", "backlog_id": "", "verify": {}}
                  for t in (plan.get("tasks") or [])],
        "created_at": _now_iso(), "updated_at": _now_iso(), "summary": "",
    }
    if data_dir and session_id:
        _save_json(card_path(data_dir, session_id), card)
    return card


def sync_from_exec(data_dir: str | Path | None, session_id: str, exec_state: Any) -> dict[str, Any]:
    """执行链推进 → 同步卡 (running/done/blocked)。exec_state: ExecState 实例或 state dict。"""
    st = exec_state.state if hasattr(exec_state, "state") else (exec_state or {})
    tasks = st.get("tasks") or []
    goal = ((st.get("plan") or {}).get("goal")) or ""
    st_status = st.get("status") or "idle"
    card = {
        "goal": str(goal or "")[:120],
        "status": st_status if st_status in VALID_STATUS else "running",
        "acceptance": (st.get("plan") or {}).get("acceptance") or [],
        "tasks": [{"title": t.get("title") or "", "priority": t.get("priority") or "P2",
                   "status": t.get("status") or "todo",
                   "backlog_id": str(t.get("backlog_id") or ""),
                   "verify": dict(t.get("verify") or {})} for t in tasks],
        "created_at": st.get("created_at") or _now_iso(),
        "updated_at": _now_iso(), "summary": "",
    }
    if data_dir and session_id:
        _save_json(card_path(data_dir, session_id), card)
    return card


def text(card: dict[str, Any]) -> str:
    """渲染成注入/查询用文本 (给模型看或 API 返回)。"""
    if not card:
        return "（暂无进度卡 — 出计划或启动执行链后自动生成）"
    goal = card.get("goal") or ""
    status = card.get("status") or "idle"
    tasks = card.get("tasks") or []
    done = sum(1 for t in tasks if t.get("status") == "done")
    lines = [f"【进度卡】{status} · {done}/{len(tasks)} 完成" + (f" · 目标: {goal}" if goal else "")]
    for t in tasks:
        mark = {"done": "✅", "running": "⏳", "verifying": "🔍", "failed": "❌",
                "todo": "⬜"}.get(t.get("status"), "⬜")
        v = t.get("verify") or {}
        lines.append(f"- {mark} {t.get('title')}"
                     + (f" [任务 {t.get('backlog_id')}]" if t.get("backlog_id") else "")
                     + (f" · 验证 {v.get('result') or 'unknown'}" if v else ""))
    acc = card.get("acceptance") or []
    if acc and any(acc):
        lines.append("验收: " + "；".join(str(a) for a in acc if a))
    return "\n".join(lines)


__all__ = ["load_card", "save_from_plan", "sync_from_exec", "text", "card_path"]
