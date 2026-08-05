"""events/store.py — SQLite append-only 事件存储 (标准库 sqlite3, 无 ORM)。

设计依据:
- phase1-plan.md §4: schema / append-only 双层保证 / 查询与回放 / WAL
- event-model.md §5.1: 语义列 (project_id/stage/action/result/evidence) 承载检索与指标

append-only 双层保证:
1. 应用层: 只暴露 append/query_*; 没有 update/delete 方法。
2. 数据库层: BEFORE UPDATE/DELETE 触发器物理拒绝 (测试验证)。

线程安全: 单连接 + RLock, 单进程内读写串行化 (WAL 支持多读单写)。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .models import Event, EventType, format_timestamp, parse_timestamp

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,   -- 单调递增, 回放锚点
    event_id   TEXT    NOT NULL UNIQUE,
    timestamp  TEXT    NOT NULL,                    -- ISO-8601 UTC (统一格式)
    type       TEXT    NOT NULL,
    source     TEXT    NOT NULL,
    project_id TEXT,
    task_id    TEXT,
    agent_id   TEXT,
    stage      TEXT,
    action     TEXT,
    result     TEXT,
    evidence   TEXT,
    payload    TEXT    NOT NULL                     -- JSON 字符串
);

CREATE INDEX IF NOT EXISTS idx_events_task_id    ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_agent_id   ON events(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_project_id ON events(project_id);
CREATE INDEX IF NOT EXISTS idx_events_type       ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_ts         ON events(timestamp);

-- append-only 数据库层保证
CREATE TRIGGER IF NOT EXISTS trg_events_no_update
BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_events_no_delete
BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
"""

_INSERT_SQL = (
    "INSERT INTO events (event_id, timestamp, type, source, project_id, task_id, agent_id,"
    " stage, action, result, evidence, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
)


class EventStore:
    """append-only 事件库。错误以"新事件"纠正 (如补发 task.end), 绝不改写旧事件。"""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        # check_same_thread=False + RLock: 单进程内多线程共享连接
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")    # 读写不互斥
            self._conn.execute("PRAGMA synchronous=NORMAL")  # 性能与安全平衡
            self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ 写入

    def append(self, event: Event) -> Event:
        """追加一条事件, 由存储层分配 seq 并回填 (frozen 模型 → model_copy 返回新实例)。"""
        with self._lock:
            with self._conn:  # 事务
                cur = self._conn.execute(_INSERT_SQL, event.to_row())
                seq = cur.lastrowid
        return event.model_copy(update={"seq": seq})

    # ------------------------------------------------------------------ 查询

    def query(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        event_type: EventType | str | None = None,
        stage: str | None = None,
        result: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        since_seq: int = 0,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Event]:
        """通用过滤查询, 全部参数可选; 结果按 seq 升序 (回放顺序)。

        时间范围 after/before 接受 UTC datetime; 统一格式下字符串比较即时间比较。
        """
        where: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            where.append("project_id = ?"); params.append(project_id)
        if task_id is not None:
            where.append("task_id = ?"); params.append(task_id)
        if agent_id is not None:
            where.append("agent_id = ?"); params.append(agent_id)
        if event_type is not None:
            t = event_type.value if isinstance(event_type, EventType) else event_type
            where.append("type = ?"); params.append(t)
        if stage is not None:
            where.append("stage = ?"); params.append(stage)
        if result is not None:
            where.append("result = ?"); params.append(result)
        if after is not None:
            where.append("timestamp >= ?"); params.append(format_timestamp(after))
        if before is not None:
            where.append("timestamp <= ?"); params.append(format_timestamp(before))
        if since_seq > 0:
            where.append("seq > ?"); params.append(since_seq)

        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seq"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
            if offset > 0:
                sql += " OFFSET ?"
                params.append(offset)
        elif offset > 0:  # OFFSET 需与 LIMIT 同现
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [Event.from_row(r) for r in rows]

    def query_events(self, *, limit: int | None = None, offset: int = 0, **filters: Any) -> Iterator[Event]:
        """CLI 预留接口 (未来 factory logs / factory status): 返回可迭代事件流, 支持 limit/offset。

        过滤器关键字与 query() 一致 (project_id/task_id/agent_id/event_type/stage/result/after/before/since_seq)。
        """
        yield from self.query(limit=limit, offset=offset, **filters)

    def by_task(self, task_id: str, since_seq: int = 0) -> list[Event]:
        """任务事件链回放: 按 seq 升序, 支持断点续跑锚点 since_seq。"""
        return self.query(task_id=task_id, since_seq=since_seq)

    def by_agent(self, agent_id: str, since_seq: int = 0) -> list[Event]:
        """Agent 事件流回放。"""
        return self.query(agent_id=agent_id, since_seq=since_seq)

    def by_project(self, project_id: str, since_seq: int = 0) -> list[Event]:
        """项目时间线回放 (Dashboard 视图 1 / 项目维度指标)。"""
        return self.query(project_id=project_id, since_seq=since_seq)

    def by_type(self, event_type: EventType | str, limit: int = 50) -> list[Event]:
        """类型过滤 (如全部 task.fail), 最近优先。"""
        t = event_type.value if isinstance(event_type, EventType) else event_type
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE type = ? ORDER BY seq DESC LIMIT ?", (t, limit)
            ).fetchall()
        return [Event.from_row(r) for r in rows]

    def recent(self, limit: int = 50) -> list[Event]:
        """最近事件流 (Dashboard 用)。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Event.from_row(r) for r in rows]

    def since(self, seq: int) -> list[Event]:
        """增量回放 (订阅者用): seq 之后的所有事件, 按 seq 升序。"""
        return self.query(since_seq=seq)

    def get(self, seq: int) -> Event | None:
        """按回放锚点取单条。"""
        with self._lock:
            row = self._conn.execute("SELECT * FROM events WHERE seq = ?", (seq,)).fetchone()
        return Event.from_row(row) if row else None

    def get_by_id(self, event_id: str) -> Event | None:
        """按全局唯一 event_id 取单条。"""
        with self._lock:
            row = self._conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return Event.from_row(row) if row else None

    def count(self) -> int:
        """事件总量。"""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        return int(row["n"])

    def count_by_type(self) -> dict[str, int]:
        """类型分布: {type: 数量}。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT type, COUNT(*) AS n FROM events GROUP BY type ORDER BY n DESC"
            ).fetchall()
        return {r["type"]: int(r["n"]) for r in rows}

    # ------------------------------------------------------------------ 生命周期

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def db_path(self) -> Path:
        return self._db_path
