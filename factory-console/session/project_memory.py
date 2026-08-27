"""factory-console/session/project_memory.py — 项目级记忆 (S-4, v1.1.219; S10-127 M3.2 升级).

Founder 2026-08-27: "新会话断链" — 跨会话记忆 + 项目知识进上下文。
S10-127 M3.2: 记忆类型化 (decision/learning/error/pattern/observation) + 权威等级
  (user_intent > verified_state > repo_evidence > agent_claim > summary) + 时间衰减。

- MemoryStore: <data_dir>/project_memory/<project_id>.json (只追加, 可审计, 来源可追溯)
- add(text, source, kind, authority): 追加记忆; recent/inject_block 按 权威*衰减 排序
- 会话话题摘要 → 记忆; 新会话"继续上次" → 注入记忆
失败安全: 文件坏/缺失 → 空记忆不崩。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .handoff import AUTHORITY, _authority_rank

MAX_ENTRIES = 200

#: 记忆类型 (passbaton 5 类 + observation 兜底)
KINDS = ("decision", "learning", "error", "pattern", "observation")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:  # noqa: BLE001 — 坏时间戳 → epoch (最旧)
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


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
    def add(self, text: str, *, source: str = "session",
            kind: str = "observation", authority: str = "agent_claim") -> None:
        """追加记忆 (去重: 相同文本不重复; 类型非法 → observation 兜底)。

        kind: decision/learning/error/pattern/observation (M3.2)
        authority: user_intent/verified_state/repo_evidence/agent_claim/summary
        """
        text = str(text or "").strip()
        if not text:
            return
        if kind not in KINDS:
            kind = "observation"
        if authority not in AUTHORITY:
            authority = "agent_claim"
        for e in self.entries:
            if e.get("text") == text:
                # 同文本: 提升权威 (更高等级才覆盖)
                if _authority_rank(authority) > _authority_rank(e.get("authority")):
                    e["authority"] = authority
                    e["kind"] = kind
                    e["ts"] = _now_iso()
                return
        self.entries.append({"text": text[:300], "source": str(source)[:40],
                             "kind": kind, "authority": authority, "ts": _now_iso()})

    def recent(self, n: int = 5) -> list[dict[str, Any]]:
        """最近 N 条 (最新在前, 按权威加权排序 — 高权威优先, 同权威按时间衰减)。"""
        now = datetime.now(timezone.utc)
        scored = []
        for e in self.entries:
            age_h = max((now - _parse_ts(e.get("ts") or "")).total_seconds() / 3600.0, 0.0)
            decay = 1.0 / (1.0 + age_h / 24.0)  # 半衰 ~24h
            rank = _authority_rank(e.get("authority"))
            scored.append((rank * 10.0 + decay, e))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:n]]

    def by_kind(self, kind: str, n: int = 5) -> list[dict[str, Any]]:
        """按类型取 (error/learning 等)。"""
        return [e for e in self.recent(n * 3) if e.get("kind") == kind][:n]

    def inject_block(self, n: int = 5) -> str:
        """注入文本块: 【项目历史记忆】 (带类型 + 权威标注)。"""
        rec = self.recent(n)
        if not rec:
            return ""
        lines = ["【项目历史记忆】(跨会话, 供参考; 标注来源等级, 低等级仅参考不作事实)"]
        for e in rec:
            kind = e.get("kind") or "observation"
            auth = e.get("authority") or "agent_claim"
            lines.append(f"- [{kind}|{auth}] {e.get('text')}")
        return "\n".join(lines)
