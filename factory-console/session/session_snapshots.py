"""factory-console/session/session_snapshots.py — T13 会话时间旅行 (轻量快照)。

会话级快照: 每轮消息后存 {round, ts, messages_slice, context_hash} 到
<data_dir>/session_snapshots/<session_id>.json (追加, 只读恢复不破坏源数据)。

- snapshot_round(): 会话每轮后调用, 记录当前消息列表长度/上下文哈希
- list_snapshots(): 列出某会话的所有快照 (前端时间旅行滑块用)
- restore_round(): 恢复到第 N 轮 — 返回该轮的消息切片 (重建会话上下文)
- 失败安全: 快照文件坏/缺失 → 空, 不崩

参考: Claude --resume / Trae 时间线 (轻量实现, 无 git 依赖; 执行级回滚仍在
execution_replay.py 负责, 本模块只做会话上下文级时间旅行)。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snap_path(data_dir: str | Path, session_id: str) -> Path:
    return Path(data_dir) / "session_snapshots" / f"{session_id}.json"


def _context_hash(messages: list[dict[str, Any]]) -> str:
    """上下文指纹: 消息 id+role+content 前 200 的哈希 (判变/去重)。"""
    h = hashlib.sha256()
    for m in messages[-20:]:
        h.update(str(m.get("id") or "").encode("utf-8", errors="ignore"))
        h.update(str(m.get("role") or "").encode("utf-8", errors="ignore"))
        h.update(str(m.get("content") or "")[:200].encode("utf-8", errors="ignore"))
    return h.hexdigest()[:16]


def snapshot_round(
    data_dir: str | Path,
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    note: str = "",
) -> dict[str, Any] | None:
    """T13: 记录一轮快照 (消息数+上下文哈希)。失败安全: 返回 None。"""
    try:
        if not data_dir or not session_id:
            return None
        path = _snap_path(data_dir, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        snaps = []
        if path.exists():
            try:
                snaps = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — 坏快照 → 从空开始
                snaps = []
        ch = _context_hash(messages)
        # 去重: 同上下文哈希不重复记 (消息未变)
        if snaps and snaps[-1].get("context_hash") == ch:
            return snaps[-1]
        snap = {
            "round": len(snaps) + 1,
            "ts": _now_iso(),
            "message_count": len(messages),
            "context_hash": ch,
            "note": str(note or "")[:120],
            "last_message": str((messages[-1].get("content") or "") if messages else "")[:120],
        }
        snaps.append(snap)
        path.write_text(json.dumps(snaps, ensure_ascii=False, indent=1), encoding="utf-8")
        return snap
    except Exception:  # noqa: BLE001 — 快照失败不阻断会话
        return None


def list_snapshots(data_dir: str | Path, session_id: str) -> list[dict[str, Any]]:
    """T13: 列出会话所有快照 (前端时间旅行滑块/列表)。失败安全: []。"""
    try:
        path = _snap_path(data_dir, session_id)
        if not path.exists():
            return []
        snaps = json.loads(path.read_text(encoding="utf-8"))
        return snaps if isinstance(snaps, list) else []
    except Exception:  # noqa: BLE001
        return []


def restore_round(
    data_dir: str | Path,
    session_id: str,
    messages: list[dict[str, Any]],
    round_no: int,
) -> list[dict[str, Any]]:
    """T13: 恢复到第 round_no 轮 — 返回该轮对应的消息切片。

    round_no 对应 snapshot_round 记录的 round; 消息切片 = 该轮 message_count
    对应的前 N 条。round_no 越界 → 返回原消息 (不破坏)。
    """
    try:
        snaps = list_snapshots(data_dir, session_id)
        if not snaps:
            return messages
        target = next((s for s in snaps if int(s.get("round") or 0) == int(round_no)), None)
        if target is None:
            return messages
        count = int(target.get("message_count") or 0)
        if count <= 0:
            return []
        return messages[:count]
    except Exception:  # noqa: BLE001
        return messages
