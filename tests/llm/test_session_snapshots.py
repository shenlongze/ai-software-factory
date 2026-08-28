"""T13 会话时间旅行 — session_snapshots 单测。

覆盖: 快照记录 / 去重 / 列表 / 恢复 / 失败安全。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _msgs(n: int) -> list[dict[str, str]]:
    return [
        {"id": f"m{i}", "role": "user" if i % 2 == 0 else "assistant", "content": f"消息 {i}"}
        for i in range(1, n + 1)
    ]


def test_snapshot_round_records(tmp_path):
    from factory_console.session.session_snapshots import snapshot_round

    snap = snapshot_round(str(tmp_path), "sess-1", _msgs(3), note="测试")
    assert snap is not None
    assert snap["round"] == 1
    assert snap["message_count"] == 3
    assert snap["context_hash"]
    path = tmp_path / "session_snapshots" / "sess-1.json"
    assert path.exists()


def test_snapshot_round_dedup(tmp_path):
    from factory_console.session.session_snapshots import snapshot_round

    msgs = _msgs(2)
    snapshot_round(str(tmp_path), "sess-1", msgs)
    # 同消息再存 → 去重 (round 不增)
    snapshot_round(str(tmp_path), "sess-1", msgs)
    snapshot_round(str(tmp_path), "sess-1", _msgs(3))
    snaps = (tmp_path / "session_snapshots" / "sess-1.json")
    import json
    assert len(json.loads(snaps.read_text(encoding="utf-8"))) == 2


def test_list_snapshots_empty_and_full(tmp_path):
    from factory_console.session.session_snapshots import list_snapshots, snapshot_round

    assert list_snapshots(str(tmp_path), "ghost") == []
    snapshot_round(str(tmp_path), "sess-2", _msgs(4))
    snaps = list_snapshots(str(tmp_path), "sess-2")
    assert len(snaps) == 1
    assert snaps[0]["message_count"] == 4


def test_restore_round(tmp_path):
    from factory_console.session.session_snapshots import restore_round, snapshot_round

    msgs = _msgs(4)
    snapshot_round(str(tmp_path), "sess-3", msgs[:2])
    snapshot_round(str(tmp_path), "sess-3", msgs)
    restored = restore_round(str(tmp_path), "sess-3", msgs, 1)
    assert len(restored) == 2
    # 越界轮次 → 返回原消息
    assert restore_round(str(tmp_path), "sess-3", msgs, 99) == msgs
    # 无快照 → 返回原消息
    assert restore_round(str(tmp_path), "ghost", msgs, 1) == msgs
