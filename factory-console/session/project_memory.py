"""factory-console/session/project_memory.py — 项目级记忆 (S-4, v1.1.219).

Founder 2026-08-27: "新会话断链" — 跨会话记忆 + 项目知识进上下文。

- MemoryStore: <data_dir>/project_memory/<project_id>.json (只追加, 可审计, 来源可追溯)
- add(text, source): 追加记忆条目; recent(n): 最近 N 条 (供注入)
- 会话话题摘要 → 记忆 (adapter 收尾写入); 新会话"继续上次" → 注入记忆
失败安全: 文件坏/缺失 → 空记忆不崩。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_ENTRIES = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, project_id: str, data: dict[str, Any] | None = None):
        self.project_id = project_id
        self.entries: list[dict[str, Any]] = list((data or {}).get("entries") or [])

    # ------------------------------------------------------------ 持久化
    @classmethod
    def load(cls, data_dir: str | Path | None, project_id: str) -> "MemoryStore":
        st = cls(project_id)
        if not data_dir or not project_id:
            return st
        try:
            d = json.loads((Path(data_dir) / "project_memory" / f"{project_id}.json").read_text(encoding="utf-8"))
            st.entries = list((d.get("entries") if isinstance(d, dict) else None) or [])
        except Exception:  # noqa: BLE001
            pass
        return st

    def save(self, data_dir: str | Path | None) -> None:
        if not data_dir or not self.project_id:
            return
        try:
            path = Path(data_dir) / "project_memory" / f"{self.project_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"project_id": self.project_id,
                                        "entries": self.entries[-MAX_ENTRIES:]},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------ 记忆操作
    def add(self, text: str, *, source: str = "session") -> None:
        """追加记忆 (去重: 相同文本不重复)。"""
        text = str(text or "").strip()
        if not text:
            return
        if any(e.get("text") == text for e in self.entries):
            return
        self.entries.append({"text": text[:300], "source": str(source)[:40],
                             "ts": _now_iso()})

    def recent(self, n: int = 5) -> list[dict[str, Any]]:
        """最近 N 条 (最新在前)。"""
        return list(reversed(self.entries[-n:]))

    def inject_block(self, n: int = 5) -> str:
        """注入文本块: 【项目历史记忆】。"""
        rec = self.recent(n)
        if not rec:
            return ""
        lines = ["【项目历史记忆】(跨会话, 供参考)"] + [
            f"- {e.get('text')} (来源: {e.get('source')})" for e in rec
        ]
        return "\n".join(lines)
