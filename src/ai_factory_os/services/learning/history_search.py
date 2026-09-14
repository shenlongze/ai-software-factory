"""history_search — 历史检索（FTS5）: 把"记得住"变成"找得回"。

背景（审计结论）: 我们有 1030 条 learning_trace / 8995 条事件 / 85 条经验，
但没有任何"翻回去用"的能力 —— 记得住但找不回 = 等于没记。

设计（借鉴 Hermes 的 session_search 思路，落在本仓库的数据形态上）:
  · 独立 search.db（FTS5 虚拟表）—— 不碰事件库 factory.db 的 schema（零风险）
  · 索引三类历史: events（发生了什么）/ traces（怎么做的）/ experiences（做成了没）
  · 检索: FTS5 全文 + 按来源/时间过滤，返回带来源与时间的命中
  · 幂等: 以 (source, ref) 为唯一键 upsert —— 重复索引不产生重复行

本模块只做【索引与检索】；"检索结果注入 LLM 上下文"属调用方（session 层）。
"""

from __future__ import annotations

import json
import re
import sys
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SOURCES: tuple[str, ...] = ("event", "trace", "experience")
DEFAULT_DB_NAME = "search.db"

_SCHEMA_VERSION = 2   # 1=external-content+触发器(错) → 2=独立表+代码侧切分

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS docs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    source  TEXT NOT NULL,
    ref     TEXT NOT NULL,
    ts      TEXT NOT NULL DEFAULT '',
    title   TEXT NOT NULL DEFAULT '',
    body    TEXT NOT NULL DEFAULT '',
    UNIQUE(source, ref)
);
-- 独立 FTS5 表（【不】用 content='docs'）: external-content 表不接受直接 INSERT ✗
-- 内容由代码写入【CJK 逐字切分后】的文本（SQL 做不到切分）
-- ★ 为什么必须切分: 本仓库的数据是密集 JSON，"旅行记账"/"非变更证据" 这类
--   连续 CJK 串在默认分词器下是【一个 token】→ 子串永远搜不到 ✗
--   （Hermes 能搜到是因为它的中文有标点/空格式分隔，我们不假设这一点）
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(title, body);
"""

#: CJK 区间 —— 索引与查询【两侧都逐字切分】
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _cjk_split(text: str) -> str:
    """CJK 逐字切分: "非变更证据" → " 非 变 更 证 据 "（非 CJK 原样保留）。"""
    return _CJK.sub(lambda m: f" {m.group(0)} ", text or "")



@dataclass(frozen=True)
class Hit:
    """一条命中 —— 带来源与时间，便于人判断"这条靠不靠谱"。"""

    source: str
    ref: str
    ts: str
    title: str
    snippet: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "ref": self.ref, "ts": self.ts,
                "title": self.title, "snippet": self.snippet}

    def render(self) -> str:
        when = self.ts[:19].replace("T", " ") if self.ts else "—"
        return f"[{self.source}] {when} {self.title}\n    {self.snippet}"


class HistoryIndex:
    """历史检索索引（FTS5）。失败安全: 任何异常都不阻断调用方。"""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._ensure_schema()

    # ---------------------------------------------------------------- 写入

    def _ensure_schema(self) -> None:
        """版本守卫 + 自愈。

        ★ 这里踩过两次坑（都真发生过）:
          ① 旧 schema 的库用 CREATE TABLE IF NOT EXISTS 建过 → 永远不修正 ✗
          ② 曾用 external-content 表 → 直接 INSERT 无效 → docs_fts 恒为 0 行 ✗
        处理: 版本不符 或 docs 有内容而 fts 为空 → 重建 FTS 表并重新填充。
        """
        try:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'").fetchone()
            ver = int(row[0]) if row else 0
            n_docs = self._conn.execute("SELECT count(*) FROM docs").fetchone()[0]
            n_fts = self._conn.execute("SELECT count(*) FROM docs_fts").fetchone()[0]
            stale = ver != _SCHEMA_VERSION or (n_docs and not n_fts)
            if stale and n_docs:
                self._conn.execute("DROP TABLE IF EXISTS docs_fts")
                self._conn.executescript(_SCHEMA)
                self._rebuild_fts()
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(_SCHEMA_VERSION),))
            self._conn.commit()
        except Exception as exc:  # noqa: BLE001 — 不静默
            print(f"[history_search] schema 自愈失败: {exc}", file=sys.stderr)

    def index_docs(self, docs: Iterable[tuple[str, str, str, str, str]]) -> int:
        """批量 upsert: (source, ref, ts, title, body) → 新增/更新条数。"""
        n = 0
        for source, ref, ts, title, body in docs:
            if not (title or body):
                continue
            cur = self._conn.execute(
                "INSERT INTO docs(source, ref, ts, title, body) VALUES(?,?,?,?,?) "
                "ON CONFLICT(source, ref) DO UPDATE SET "
                "ts=excluded.ts, title=excluded.title, body=excluded.body",
                (source, ref, ts, title, body))
            if cur.rowcount:
                # FTS 表存【归一化文本】（CJK 逐字切分），docs 表存原文供展示
                self._conn.execute("DELETE FROM docs_fts WHERE rowid=?", (cur.lastrowid,))
                self._conn.execute(
                    "INSERT INTO docs_fts(rowid, title, body) VALUES(?,?,?)",
                    (cur.lastrowid, _cjk_split(f"{title} {body}")))
            n += 1
        self._conn.commit()
        return n

    def sync_from_data_dir(self, data_dir: Path | str) -> dict[str, int]:
        """从数据根索引三类历史。幂等（UNIQUE 键）。"""
        root = Path(data_dir)
        counts = {s: 0 for s in SOURCES}
        counts["event"] = self._index_events(root)
        counts["trace"] = self._index_traces(root)
        counts["experience"] = self._index_experiences(root)
        self._conn.commit()
        self._rebuild_fts()          # 统一重建 FTS（归一化文本）
        return counts

    def _rebuild_fts(self) -> None:
        """用 docs 表原文重建 FTS 内容（归一化: CJK 逐字切分）。幂等。"""
        try:
            self._conn.execute("DELETE FROM docs_fts")
            for rowid, title, body in self._conn.execute("SELECT id, title, body FROM docs"):
                self._conn.execute(
                    "INSERT INTO docs_fts(rowid, title, body) VALUES(?,?,?)",
                    (rowid, _cjk_split(title), _cjk_split(body)))
        except Exception:  # noqa: BLE001
            pass

    def _index_events(self, root: Path) -> int:
        """事件库: 只读打开 factory.db（绝不写它）。"""
        db = root / "factory.db"
        if not db.exists():
            return 0
        n = 0
        try:
            src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cols = [r[1] for r in src.execute("PRAGMA table_info(events)")]
            tcol = "ts" if "ts" in cols else ("created_at" if "created_at" in cols else None)
            seq = "seq" if "seq" in cols else None
            ts_expr = tcol or "''"
            sel = f"select {seq or 'rowid'}, {ts_expr}, * from events"
            for row in src.execute(sel):
                ref = str(row[0])
                ts = str(row[1] or "")
                kv = dict(zip(cols, row[2:])) if len(row) >= len(cols) else {}
                etype = str(kv.get("type") or "")
                esource = str(kv.get("source") or "")
                title_txt = f"{etype} ({esource})" if etype else f"event#{ref}"
                rest = " ".join(str(x) for x in row[2:] if x is not None)
                self._conn.execute(
                    "INSERT INTO docs(source, ref, ts, title, body) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(source, ref) DO UPDATE SET ts=excluded.ts, body=excluded.body",
                    ("event", ref, ts, title_txt, rest[:6000]))
                n += 1
            src.close()
        except Exception:  # noqa: BLE001 — 事件库不可读 → 跳过（不阻断）
            return n
        return n

    def _index_traces(self, root: Path) -> int:
        f = root / "memory" / "learning_trace.json"
        if not f.exists():
            return 0
        n = 0
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("traces", [])
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    continue
                ref = str(it.get("trace_id") or it.get("id") or f"trace-{i}")
                ts = str(it.get("ts") or it.get("timestamp") or "")
                title = str(it.get("kind") or it.get("type") or it.get("event") or "trace")
                body = json.dumps(it, ensure_ascii=False)
                self._conn.execute(
                    "INSERT INTO docs(source, ref, ts, title, body) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(source, ref) DO UPDATE SET ts=excluded.ts, body=excluded.body",
                    ("trace", ref, ts, title, body[:6000]))
                n += 1
        except Exception:  # noqa: BLE001
            return n
        return n

    def _index_experiences(self, root: Path) -> int:
        f = root / "memory" / "experience_store.json"
        if not f.exists():
            return 0
        n = 0
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("experiences", [])
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    continue
                ref = str(it.get("id") or it.get("experience_id") or f"exp-{i}")
                ts = str(it.get("ts") or it.get("created_at") or "")
                title = str(it.get("task") or it.get("objective") or it.get("kind") or "experience")
                body = json.dumps(it, ensure_ascii=False)
                self._conn.execute(
                    "INSERT INTO docs(source, ref, ts, title, body) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(source, ref) DO UPDATE SET ts=excluded.ts, body=excluded.body",
                    ("experience", ref, ts, title, body[:6000]))
                n += 1
        except Exception:  # noqa: BLE001
            return n
        return n

    # ---------------------------------------------------------------- 检索

    def search(self, query: str, *, limit: int = 8,
               sources: tuple[str, ...] | None = None) -> list[Hit]:
        """FTS5 全文检索。空查询/无命中 → 空列表（不抛）。"""
        terms = _fts_terms(query)
        if not terms:
            return []
        where = ""
        params: list[Any] = []
        if sources:
            where = f" AND d.source IN ({','.join('?' * len(sources))})"
            params.extend(sources)
        sql = (
            "SELECT d.source, d.ref, d.ts, d.title, d.body "
            "FROM docs_fts f JOIN docs d ON d.id = f.rowid "
            f"WHERE docs_fts MATCH ?{where} ORDER BY rank LIMIT ?"
        )
        try:
            rows = self._conn.execute(sql, [terms, *params, limit]).fetchall()
        except Exception:  # noqa: BLE001 — 语法/库异常 → 空结果（失败安全）
            return []
        return [Hit(source=r[0], ref=r[1], ts=r[2] or "", title=r[3] or "",
                    snippet=_snippet(r[4] or "", terms)) for r in rows]

    def _rebuild_fts(self) -> None:
        """按 CJK 切分重建 FTS（幂等）。"""
        try:
            self._conn.execute("DELETE FROM docs_fts")
            for rowid, title, body in self._conn.execute("SELECT id, title, body FROM docs"):
                self._conn.execute(
                    "INSERT INTO docs_fts(rowid, title, body) VALUES(?,?,?)",
                    (rowid, _cjk_split(title), _cjk_split(body)))
            self._conn.commit()
        except Exception as exc:  # noqa: BLE001 — 不静默
            print(f"[history_search] FTS 重建失败: {exc}", file=sys.stderr)

    def stats(self) -> dict[str, int]:
        """各类历史已索引条数。"""
        out = {s: 0 for s in SOURCES}
        out["total"] = 0
        try:
            for src, n in self._conn.execute("SELECT source, count(*) FROM docs GROUP BY source"):
                out[src] = n
                out["total"] += n
        except Exception:  # noqa: BLE001
            pass
        return out

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


#: CJK 区间（汉字 + 常用中文标点/全角）—— 这些字符在索引与查询时逐字切分。
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _cjk_split(text: str) -> str:
    """CJK 逐字切分: "这是记账" → "这 是 记 账"（非 CJK 原样保留）。

    unicode61 因此按【字】成词 → 2 字词（"截图"/"记账"）能以短语命中 ✓
    """
    return _CJK.sub(lambda m: f" {m.group(0)} ", text or "")


def _fts_terms(query: str) -> str:
    """查询 → FTS5 表达式。

    索引侧已把 CJK 逐字切分（"非变更证据" → "非 变 更 证 据"），查询侧必须匹配。
    分三种情况:
      · 短中文词（≤4 字）: 整词短语 —— "记账" → "\"记 账\""（精准）
      · 长中文串/句子: 切 2 字滑窗并【OR】—— 会话里用户说的是句子，
        整句成一个短语必然 0 命中 ✗，按词窗 OR 才召回得到 ✓（注入场景召回优先）
      · 非 CJK 词: 原样加引号
    """
    q = (query or "").strip()
    if not q:
        return ""
    parts: list[str] = []
    for raw in re.split(r"\s+", q):
        raw = raw.strip()
        if not raw:
            continue
        if not _CJK.search(raw):
            parts.append('"' + raw.replace('"', "") + '"')
            continue
        chars = [c for c in _cjk_split(raw).split()]
        if len(chars) <= 4:
            parts.append('"' + " ".join(chars) + '"')
        else:
            # 2 字滑窗（中文词的常见长度）→ OR
            for k in range(len(chars) - 1):
                parts.append('"' + chars[k] + " " + chars[k + 1] + '"')
    if not parts:
        return ""
    # OR: 长查询按窗口并列（召回优先）；单短语直接用
    return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts[:12]) + ")"


#: 从 payload JSON 里提炼可读摘要时优先取的键（按语义重要性排序）。
_SUMMARY_KEYS = ("name", "goal", "title", "task", "objective", "description", "problem",
                 "action", "result", "summary", "message", "reason", "phase", "status",
                 "project_id", "task_id", "agent_id", "model", "verdict", "decision")


def _extract_json_obj(body: str) -> dict | None:
    """从事件 body（"seq id ts type source ... {json}"）里取出 JSON 对象。"""
    at = body.find("{")
    while at >= 0:
        try:
            obj = json.loads(body[at:])
            if isinstance(obj, dict):
                return obj
        except Exception:  # noqa: BLE001 — 不是完整 JSON → 继续找下一个 {
            pass
        at = body.find("{", at + 1)
    return None


def _summarize_payload(body: str, *, width: int = 150) -> str:
    """把 payload JSON 提炼成人能读的一行摘要（不吐原始 JSON）。

    例: {"project_id":"P-2f622bdf","name":"旅行记账","goal":"旅行支出乱"}
      → P-2f622bdf · 旅行记账 · 旅行支出乱
    """
    obj = _extract_json_obj(body)
    if not obj:
        return ""
    bits: list[str] = []
    for k in _SUMMARY_KEYS:
        v = obj.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (str, int, float)):
            s = str(v)
        elif isinstance(v, list):
            s = ", ".join(str(x) for x in v[:3] if isinstance(x, (str, int, float)))
        else:
            continue
        if s:
            bits.append(s)
        if len(" · ".join(bits)) >= width:
            break
    return " · ".join(bits)[:width]


def _snippet(body: str, terms: str, *, width: int = 180) -> str:
    """命中片段 = 【可读摘要】优先，其次命中位置上下文，最后开头。

    为什么: 事件 body 是 "seq id ts type source {json}" 这样的原始文本，
    直接吐出来对 LLM/人都没用（实测注入内容全是 7720 f07098... ✗）。
    """
    summary = _summarize_payload(body, width=width)
    if summary:
        return summary
    flat = " ".join((body or "").split())
    probe = [w.strip('"').replace(" ", "") for w in terms.split(" AND ")]
    at = -1
    for pw in probe:
        if pw:
            at = flat.find(pw)
            if at >= 0:
                break
    if at < 0:
        return flat[:width]
    lo = max(0, at - width // 3)
    return ("…" if lo else "") + flat[lo:lo + width] + "…"
