# Phase 1 开发计划 — Event Logger MVP

> 版本: v0.1 | 日期: 2026-08-05 | 状态: 待执行
> 关联文档: [prd.md](./prd.md) · [roadmap.md](./roadmap.md) · [design/migration-plan.md](./design/migration-plan.md) · [design/runtime-design.md](./design/runtime-design.md)

---

## 1. 目标与范围

**目标**: 落地 Event Logger 最小可用版本 —— 六类事件、SQLite append-only 存储、指标聚合、pytest 全绿。回答三个问题: 系统在做什么 / 做过什么 / 结果如何。

**铁律**: 只读观测,不改任何 Agent 行为。加"记录"不加"干预"。

**范围**:
- ✅ Event 模型 (Pydantic) / SQLite 存储 / 查询与回放 / 指标聚合 / 测试
- ❌ CLI、Dashboard (Phase 2)、Task Manager (Phase 3)、事件异步分发 (订阅者模式, MVP 只做持久化)

**技术栈**: Python 3.12+ / Pydantic v2 / SQLite (标准库 `sqlite3`,WAL 模式) / pytest。

---

## 2. 文件结构

```
ai-software-factory/
├── pyproject.toml              # 项目配置 + pytest + ruff (新增)
├── factory-core/
│   └── events/
│       ├── __init__.py         # 对外出口: EventLogger, Event, EventType, compute_metrics
│       ├── models.py           # Pydantic: EventType 枚举 + Event 模型
│       ├── store.py            # SQLite append-only 存储 + 查询
│       ├── logger.py           # 高层 API: record_event() / 线程安全封装
│       └── metrics.py          # 指标聚合 (从事件计算,不另建表)
└── tests/
    └── events/
        ├── conftest.py         # tmp_path 临时事件库 fixture
        ├── test_models.py      # 模型校验
        ├── test_store.py       # append-only 语义 + 查询
        ├── test_logger.py      # 端到端六类事件
        └── test_metrics.py     # 指标聚合正确性
```

`factory-core/` 下其余模块 (task/agent/skill/workflow...) 留空占位,Phase 3 再填充。

---

## 3. Pydantic 模型定义 (`factory-core/events/models.py`)

### 3.1 EventType (六类最小事件)

```python
from enum import Enum

class EventType(str, Enum):
    TASK_START   = "task.start"     # 任务开始: 任务定义、目标、开始时间
    TASK_END     = "task.end"       # 任务结束: 结果(done/failed)、耗时、产物指针
    TASK_FAIL    = "task.fail"      # 任务失败: 失败阶段、错误摘要、证据指针
    TOOL_CALL    = "tool.call"      # 工具调用: 工具名、参数摘要、结果摘要、耗时
    CHECKPOINT   = "checkpoint"     # 停靠点落盘: 停靠点描述、落盘产物清单 (续跑生命线)
    SESSION_CLOSE = "session.close" # 会话结束: 事件数、任务数、成败统计
```

> 与 runtime-design §2.2 的完整分类 (task.created / validation.passed / human.* 等) 的关系: MVP 用六类最小集,`type` 字段直接存字符串,后续扩类**不改表结构** (加枚举成员即可)。Phase 3+ 按需扩展。

### 3.2 Event

```python
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

class Event(BaseModel):
    """一条事件。append-only: 写入后永不修改、永不删除。"""

    event_id: str = Field(default_factory=lambda: uuid4().hex)  # 全局唯一
    seq: int = 0                      # 单调递增序号,由存储层分配 (回放锚点)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: EventType                   # 事件类型 (六类)
    source: str                       # 发布模块,如 "cli" / "orchestrator" / "agent"
    agent_id: Optional[str] = None    # 与 Agent 相关时必填
    task_id: Optional[str] = None     # 与任务相关时必填
    payload: dict[str, Any] = Field(default_factory=dict)  # 类型相关载荷,JSON 友好

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v):
        return EventType(v) if isinstance(v, str) else v

    @field_validator("payload")
    @classmethod
    def _payload_json_safe(cls, v):
        json.dumps(v)   # 序列化失败则抛错,拒绝入库
        return v

    def to_row(self) -> tuple:
        """转 SQLite 行。"""
        return (
            self.event_id, self.timestamp.isoformat(), self.type.value,
            self.source, self.agent_id, self.task_id,
            json.dumps(self.payload, ensure_ascii=False),
        )
```

**模型要点**:
- `seq` 由存储层分配,模型内默认 0,插入后回填 (Pydantic `model_copy(update=...)`)。
- `payload` 必须是 JSON 可序列化 (校验即拒)。
- 时间统一 UTC ISO-8601,排序与聚合不歧义。

---

## 4. SQLite 存储层设计 (`factory-core/events/store.py`)

### 4.1 Schema

```sql
CREATE TABLE IF NOT EXISTS events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,   -- 单调递增,回放锚点
    event_id   TEXT    NOT NULL UNIQUE,
    timestamp  TEXT    NOT NULL,                    -- ISO-8601 UTC
    type       TEXT    NOT NULL,
    source     TEXT    NOT NULL,
    agent_id   TEXT,
    task_id    TEXT,
    payload    TEXT    NOT NULL                     -- JSON 字符串
);

CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_type    ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_ts      ON events(timestamp);
```

### 4.2 append-only 保证 (双层)

1. **应用层**: `EventStore` 只暴露 `append()` / `query_*()`;**没有 update / delete 方法**。这是第一道闸。
2. **数据库层**: 建库后执行触发器,物理拒绝 UPDATE/DELETE (测试验证):

```sql
CREATE TRIGGER IF NOT EXISTS trg_events_no_update
BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_events_no_delete
BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
```

> 错误以"新事件"纠正 (如补发 `task.end`),绝不改写旧事件。

### 4.3 写入 (KISS,同步优先)

```python
class EventStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")   # 读写不互斥
        self._conn.execute("PRAGMA synchronous=NORMAL") # 性能与安全的平衡
        self._init_schema()

    def append(self, event: Event) -> Event:
        """追加一条事件,分配 seq 并回填。线程安全由外部锁保证 (见 logger)。"""
        with self._conn:  # 事务
            cur = self._conn.execute(
                "INSERT INTO events (event_id, timestamp, type, source, agent_id, task_id, payload)"
                " VALUES (?,?,?,?,?,?,?)", event.to_row())
            seq = cur.lastrowid
        return event.model_copy(update={"seq": seq})
```

### 4.4 查询与回放 (只读)

| 方法 | 用途 | SQL 要点 |
|------|------|----------|
| `get(seq)` / `get_by_id(event_id)` | 单条查询 | 主键 / unique 索引 |
| `by_task(task_id, since_seq=0)` | 任务事件链回放 | `WHERE task_id=? AND seq>? ORDER BY seq` |
| `by_type(type, limit)` | 类型过滤 (如全部 task.fail) | `WHERE type=? ORDER BY seq DESC LIMIT ?` |
| `recent(limit=50)` | 最近事件流 (Dashboard 用) | `ORDER BY seq DESC LIMIT ?` |
| `since(seq)` | 增量回放 (订阅者用) | `WHERE seq>? ORDER BY seq` |
| `count()` / `count_by_type()` | 总量与分布 | `COUNT(*) GROUP BY type` |

### 4.5 会话轮转 (防膨胀)

事件库按 `events/<project_id>/<session_id>.db` 存放;单库建议上限 10 万条,超出提示归档 (`factory logs --archive` 导出聚合指标后轮转,Phase 2 实现 CLI 入口)。

---

## 5. 指标聚合 (`factory-core/events/metrics.py`)

**原则: 指标 = 事件聚合,不单独建统计表** (避免双写不一致)。全部为纯函数,输入事件列表,输出指标。

```python
def compute_metrics(events: Sequence[Event], *, group_by: str = "day") -> Metrics:
    """按 group_by (day|session|all) 聚合:
    - task_count / success_count / fail_count / success_rate
    - avg_task_duration_s / avg_retry_count (同一 task_id 的 task.start 次数-1)
    - tool_call_count / avg_tool_calls_per_task
    - interrupted_count (checkpoint 后无 task.end 的任务数)
    """
```

实现要点 (KISS):
- 遍历一次事件流,按 `group_by` 键分组,状态放在局部 dict,不落库。
- `task 耗时` = 该 task_id 的 `task.end.timestamp − task.start.timestamp`。
- `重试次数` = 同一 task_id 的 `task.start` 次数 − 1。
- `success_rate` = `task.end` (payload.result=="done") / (`task.end` + `task.fail`)。
- `session.close` 的 payload 自带会话统计 (事件数/任务数/成败),聚合时可直接引用。
- 输出 `Metrics` (Pydantic model),支持 `to_markdown()` 供 Phase 2 Dashboard 直接渲染。

---

## 6. 高层 API (`factory-core/events/logger.py`)

```python
class EventLogger:
    """线程安全的统一入口。全项目只通过它发事件。"""

    def __init__(self, store: EventStore):
        self._store = store
        self._lock = threading.Lock()

    def record(self, type: EventType, *, source: str,
               task_id: str | None = None, agent_id: str | None = None,
               payload: dict | None = None) -> Event:
        with self._lock:
            return self._store.append(Event(type=type, source=source, ...))

    # 六类事件便捷方法 (KISS: 每类一个,参数即该事件必需字段)
    def task_start(self, task_id, title, role) -> Event: ...
    def task_end(self, task_id, result: str, duration_s: float, artifact: str | None) -> Event: ...
    def task_fail(self, task_id, stage: str, error: str, evidence: str | None) -> Event: ...
    def tool_call(self, task_id, tool: str, arg_summary, result_summary, duration_s) -> Event: ...
    def checkpoint(self, task_id, description: str, artifacts: list[str]) -> Event: ...
    def session_close(self, session_id: str) -> Event: ...
```

**性能策略 (对齐迁移方案)**: MVP 同步写入 (SQLite 单条插入 ~微秒级,可接受);若实测影响主流程,升级为内存队列 + 后台批量 flush (预留 `logger.py` 接口,实现细节 Phase 1 收尾时按压力测试决定)。

---

## 7. 测试计划 (pytest)

### 7.1 测试文件与覆盖点

| 文件 | 覆盖点 |
|------|--------|
| `test_models.py` | ① 合法事件构造成功;② 非法 `type` 拒绝;③ 非 JSON payload 拒绝;④ 默认值 (timestamp/event_id/seq=0);⑤ `to_row()` 序列化正确 |
| `test_store.py` | ① append 后 seq 单调递增;② **UPDATE/DELETE 被触发器拒绝**;③ 重复 event_id 拒绝 (UNIQUE);④ 按 task_id 回放顺序正确;⑤ 按 type/时间过滤;⑥ `since(seq)` 增量回放;⑦ WAL 模式生效;⑧ 库文件真实落盘、重开可读 (持久化) |
| `test_logger.py` | ① 六类便捷方法端到端写入并回读;② 同一 task_id 的 start→tool.call→checkpoint→end 事件链完整;③ 多线程并发写 100 条无丢失、seq 无重复;④ 字段可空性 (agent_id/task_id 为 None 时正常) |
| `test_metrics.py` | ① 成功率计算正确 (含失败任务);② 耗时 = end−start;③ 重试计数正确 (同一任务 start 2 次 = 1 次重试);④ 按 day/session 分组正确;⑤ 空事件流返回零值不报错 |

### 7.2 运行方式

```bash
cd /Users/Shared/work/ai-software-factory
python3 -m venv .venv && source .venv/bin/activate   # PEP 668 环境
pip install -e ".[dev]"                               # pydantic + pytest + ruff
pytest tests/ -v                                      # 全部绿
```

---

## 8. 开发任务拆解

| # | 任务 | 交付物 | 验收 | 预估 |
|:-:|------|--------|------|:----:|
| T1 | 项目脚手架 | `pyproject.toml` (pyproject 元数据 + `[dev]` 依赖)、`factory-core/__init__.py`、`tests/conftest.py` | `pip install -e ".[dev]"` 成功;pytest 可收集到测试 | 0.5 人天 |
| T2 | 事件模型 | `events/models.py` (EventType + Event) | test_models.py 全绿 | 0.5 人天 |
| T3 | SQLite 存储 | `events/store.py` (schema/append/查询/触发器) | test_store.py 全绿 (含 append-only 断言) | 1 人天 |
| T4 | Logger API | `events/logger.py` (record + 六类便捷方法,线程安全) | test_logger.py 全绿 (含并发写) | 0.5 人天 |
| T5 | 指标聚合 | `events/metrics.py` (compute_metrics + Metrics 模型 + to_markdown) | test_metrics.py 全绿 | 1 人天 |
| T6 | 收尾验收 | 行为基线对比 (改造前后 Agent 行为无差异)、文档更新、git 提交 | 见 §9 验收清单 | 1 人天 |

**合计: 4.5 人天 ≈ 1 个迭代。**

**执行顺序**: T1 → T2 → T3 → T4 → T5 → T6 (严格依赖,不可并行)。

---

## 9. 验收清单 (全部满足才算 Phase 1 完成)

- [ ] `pytest tests/ -v` 全绿 (测试数 ≥ 25)
- [ ] 六类事件均可写入并回读;`UPDATE/DELETE` 被拒绝 (append-only 验证通过)
- [ ] 任一失败任务,能按 task_id 回放出失败前的完整事件链
- [ ] 能回答"当前在做什么任务、已耗时多久、做过哪些步骤" (来自最近 checkpoint + tool.call 事件)
- [ ] 连续 3 个会话的指标 (成功率/耗时/重试) 可对比 (`compute_metrics(group_by="session")`)
- [ ] 全程未改变任何 Agent 行为 (对照行为基线: 同一任务改造前后输出一致)
- [ ] 事件写入对主流程无感知延迟 (同步写实测;超标则启用队列方案)
- [ ] 代码通过 ruff 检查;git 提交包含三份文档 (prd/roadmap/phase1-plan)

---

## 10. 风险与对策 (MVP 版)

| 风险 | 对策 |
|------|------|
| 日志噪音 | 只记六类事件;噪音超了先砍事件类型,不加过滤规则 |
| 存储膨胀 | 按会话分库 + 10 万条阈值提示归档;聚合指标保留 |
| 写入拖慢主流程 | 先同步后实测;超标升级为内存队列 + 后台批量 flush |
| 并发写冲突 | `threading.Lock` 串行化写入 (单进程内),SQLite WAL 支持多读单写 |
| 与设计稿命名漂移 | 类型枚举对齐 migration-plan 六类;字段对齐 runtime-design §4.3 (event_id/seq/timestamp/type/source/agent_id/task_id/payload) |

---

*执行入口: T1 脚手架。完成后回到 [roadmap.md](./roadmap.md) 进入 Phase 2。*
