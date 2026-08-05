# AI Software Factory — Event 模型

> 版本: v1.0 | 状态: 设计稿
> 关联文档: [runtime-design](./design/runtime-design.md)、[validation-model](./design/validation-model.md)、[cli-design](./cli-design.md)、[dashboard-design](./dashboard-design.md)
> 存储: SQLite(events 表为唯一强制持久化;其余均为投影/派生)
> 设计原则: append-only、事件即事实、指标从事件算、事件有来源。

---

## 1. 核心原则

| 原则 | 含义 | 落地 |
|---|---|---|
| **append-only** | 事件只追加,不修改、不删除 | 错误以"新事件"纠正(如 `task.failed` 后再 `task.resumed`),绝不 UPDATE/DELETE 旧事件 |
| **事件即事实(唯一事实源)** | 系统状态 = 事件流投影;`tasks/agents/projects` 的当前状态全部由事件重放得到 | 任何模块不互读状态,只发布事件、订阅事件 |
| **事件有来源** | 每个事件带 `source`(模块)与 `agent_id`/`task_id`(若非系统事件) | 支撑审计、追溯、指标分组 |
| **指标从事件算** | 不另建统计表;first_attempt_success / path_errors / human_intervention 均由 events 表聚合(§6) | Dashboard、`factory metrics` 直接跑 SQL |
| **可回放** | 任意时刻可从 seq=1 或 since_seq 重放重建任意历史状态 | `replay()` 纯函数,用于审计、恢复、复盘 |

---

## 2. Event 结构

### 2.1 字段定义

```jsonc
{
  "event_id":   "E-10086",                    // 全局唯一
  "seq":        10086,                        // 全局单调递增,回放锚点
  "timestamp":  "2026-08-05T10:32:10Z",       // ISO8601 UTC
  "type":       "validation.failed",          // 六类事件之一,见 §3
  "source":     "validation_engine",          // 发布模块:task_manager / agent / agent_registry / validation_engine / workflow_engine / orchestrator / cli
  "project_id": "P-markpad",                  // 可选:项目维度
  "task_id":    "T-042",                      // 可选:任务维度
  "agent_id":   "A-012",                      // 可选:Agent 维度
  "stage":      "verifying",                  // 事件发生时对象的状态/阶段(见 §2.2)
  "action":     "independent verify L2",      // 动作简述(自然语言, 检索友好)
  "result":     "FAIL",                       // 判定结果,枚举见 §2.2
  "evidence":   "ref://artifacts/T-042/val-3.log",  // 证据引用(可回查)
  "payload":    { "failure_class": "code_error" }   // 类型相关扩展载荷(JSON)
}
```

### 2.2 四个语义列(stage / action / result / evidence)

为支撑"按字段检索 + 指标聚合",四列固定语义,不放进 payload:

| 列 | 语义 | 取值示例 |
|---|---|---|
| `stage` | 事件发生时对象的状态或流程阶段 | task:`pending/assigned/running/verifying/done/blocked/failed`;agent:`idle/running/blocked/stopped`;验证:`L1/L2/L3`;流程:`需求/架构/开发/测试/构建/验收` |
| `action` | 做了什么(自然语言,一行) | `run tests`、`patch history.dart`、`delegate T-042 → A-012` |
| `result` | 判定结果(枚举,可机读) | `OK / PASS / FAIL / ERROR / blocked / approve / reject / rework / abort / acquired / released` |
| `evidence` | 证据引用,`ref://` 或文件路径 | `ref://artifacts/T-042/val-3.log`、`ref://git:P-markpad@HEAD` |

其余类型相关字段一律进 `payload`(JSON,键为 `snake_case`)。

### 2.3 必填约束

- 必填:`event_id / seq / timestamp / type / source`
- `task_id` 必填的事件类型:`task.* / validation.* / workflow.gate_*`(gate 与锁无任务时允许空)
- `agent_id` 必填的事件类型:`agent.* / task.reported`(自报来自 Agent)
- `result` 必填的事件类型:`task.* / validation.* / workflow.gate_* / human.*`
- 校验失败的事件拒绝入库,由发布方修正后重发(发出 `system.metric` 记录一次校验失败计数)。

---

## 3. 六类事件字典

> 事件名与 runtime-design §2.2 一致;`stage/action/result` 列给出该事件的约定取值。

### 3.1 任务类(`task.*`)— 触发方:Task Manager / Agent / Orchestrator

| 事件 | stage | result | 载荷要点(payload) | 含义 |
|---|---|---|---|---|
| `task.created` | pending | OK | title, role, dependencies, acceptance[], scope{allowed,forbidden} | 定义任务 |
| `task.assigned` | assigned | OK | agent_id, context 引用 | 委派(含断点续跑委派) |
| `task.reported` | verifying | PASS/FAIL | summary, files[] | Agent 自报(验证的输入,非结论) |
| `task.completed` | done | PASS | acceptance 核对结果 | 双验证通过,任务完成 |
| `task.failed` | failed | api_error/env_error/path_error/context_error/code_error | reason, attempts | 失败(必须带失败分类,见 validation-model §4.2) |
| `task.blocked` | blocked | G1/G2/G3 | reason, gate | 命中三挡板暂停 |
| `task.resumed` | assigned | approve/rework | decision 引用 | 恢复执行 |
| `task.cancelled` | cancelled | abort | reason | 终止 |

### 3.2 Agent 类(`agent.*`)— 触发方:Agent Registry / Agent

| 事件 | stage | result | 载荷要点 | 含义 |
|---|---|---|---|---|
| `agent.started` | running | OK | role, skill{name,version}, task_id, tool_call_limit | 实例化并绑定任务 |
| `agent.action` | running | OK/ERROR | tool, files[], action 详情 | 每个关键动作(检索/改文件/跑命令) |
| `agent.summary` | — | OK | 阶段性小结 | 中间小结(可选;终报走 `task.reported`) |
| `agent.stopped` | idle/stopped | OK/ERROR | reason, tool_call_count | 停止(完成/异常/截断) |

### 3.3 验证类(`validation.*`)— 触发方:Validation Engine / Orchestrator

| 事件 | stage | result | 载荷要点 | 含义 |
|---|---|---|---|---|
| `validation.started` | L1/L2/L3 | started | check 列表 | 独立验证开始(级别见 validation-model §2) |
| `validation.passed` | L1/L2/L3 | PASS | 逐项证据, evidence[] | 独立验证通过 |
| `validation.failed` | L1/L2/L3 | FAIL | failure_class, reason, evidence | 独立验证失败 |
| `validation.blocked` | — | blocked | forbidden 文件列表 | 越权拦截(写了 Forbidden 范围) |

### 3.4 工作流类(`workflow.*`)— 触发方:Workflow Engine

| 事件 | stage | result | 载荷要点 | 含义 |
|---|---|---|---|---|
| `workflow.gate_opened` | 阶段名 | opened | gate 名 | 闸门开启(如进入验证门) |
| `workflow.gate_passed` | 阶段名 | PASS | gate 名 | 闸门通过,自动推进 |
| `workflow.gate_blocked` | 阶段名 | blocked | gate 名, reason | 闸门拦截(挡板或校验失败) |
| `workflow.lock_acquired` | — | acquired | resource | 获取文件锁(串行纪律) |
| `workflow.lock_released` | — | released | resource | 释放文件锁 |

### 3.5 系统类(`system.*`)— 触发方:任意模块

| 事件 | stage | result | 载荷要点 | 含义 |
|---|---|---|---|---|
| `system.checkpoint` | 阶段名 | OK | checkpoint_ref, git_sha, files_sha256{} | 断点(恢复锚点,记文件哈希) |
| `system.interrupted` | — | ERROR | reason(截断/会话中断), tool_calls | 截断记录(治理指标来源) |
| `system.resumed` | — | OK | from_seq, checkpoint_ref | 恢复完成 |
| `system.metric` | — | OK | key, value | 任意键值指标(工具调用数、配置变更等) |

### 3.6 人工类(`human.*`)— 触发方:Orchestrator(PO 决策入口)

| 事件 | stage | result | 载荷要点 | 含义 |
|---|---|---|---|---|
| `human.review_requested` | blocked | requested | gate, reason, evidence 链 | 请求人工裁决(挡板/授权/第 3 次失败) |
| `human.decision` | 决策后状态 | approve/reject/rework/abort | decision 引用, owner | PO 决策 |
| `human.intervention` | — | OK | reason | 人工主动介入记录(如手动修环境) |

---

## 4. 唯一事实源原则(落地规则)

1. **状态一律投影**:`tasks.status`、`agents.current_task_id`、里程碑进度等任何"当前状态",只允许从 events 表重放计算,禁止模块间直接读对方内存/文件状态。
2. **纠错发新事件**:发现写错(如 `task.assigned` 委派错了人)→ 发 `task.resumed`/新事件纠正,不 UPDATE 旧行。证据链保持完整。
3. **事件先落库再行动**:发布方"先 append 事件,再执行后续动作";读取方"只认事件库,不认口头状态"。CLI 的写命令同理(见 cli-design §1.3)。
4. **投影可重建**:tasks/agents/projects 表只是**派生缓存**,删除后可由事件流全量重建;任何时刻不一致,以重放结果为准。
5. **证据必须可回查**:`evidence` 指向的产物(日志/测试输出/截图)保留在 `artifacts/`,事件库不存大对象。

---

## 5. SQLite 表结构

### 5.1 events 表(唯一强制持久化)

```sql
PRAGMA journal_mode = WAL;              -- 读写并发友好

CREATE TABLE IF NOT EXISTS events (
  event_id   TEXT PRIMARY KEY,          -- E-10086
  seq        INTEGER NOT NULL UNIQUE,   -- 全局单调递增,回放锚点
  timestamp  TEXT NOT NULL,             -- ISO8601 UTC (2026-08-05T10:32:10Z)
  type       TEXT NOT NULL,             -- task.assigned / validation.failed / ...
  source     TEXT NOT NULL,             -- 发布模块
  project_id TEXT,                      -- 可选
  task_id    TEXT,                      -- 可选
  agent_id   TEXT,                      -- 可选
  stage      TEXT,                      -- 状态/阶段(见 §2.2)
  action     TEXT,                      -- 动作简述
  result     TEXT,                      -- 判定结果
  evidence   TEXT,                      -- 证据引用 ref://...
  payload    TEXT,                      -- JSON 扩展载荷
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 写入唯一入口:INSERT ... RETURNING seq;seq 由 AUTOINCREMENT 序列分配,冲突即重试。

CREATE INDEX idx_events_seq          ON events(seq);
CREATE INDEX idx_events_project      ON events(project_id, seq);
CREATE INDEX idx_events_task         ON events(task_id, seq);
CREATE INDEX idx_events_agent        ON events(agent_id, seq);
CREATE INDEX idx_events_type         ON events(type, timestamp);
CREATE INDEX idx_events_timestamp    ON events(timestamp);
CREATE INDEX idx_events_stage_result ON events(stage, result);
```

索引用途:`seq` 回放锚点;`(project_id, seq)` 项目时间线(Dashboard 视图 1);`(task_id, seq)` 任务时间线(视图 2 与恢复);`(agent_id, seq)` Agent 面板(视图 3);`(type, timestamp)` 日志过滤;`(stage, result)` 指标聚合(如 `stage='failed'`)。

### 5.2 投影表(派生缓存,可重建)

> 由事件重放增量维护;schema 只存"查询需要但重放成本高"的字段,状态字段在每次事件落库后同步更新。

```sql
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  workflow   TEXT NOT NULL,             -- 绑定流程名
  repo       TEXT,
  status     TEXT DEFAULT 'active',     -- active|archived
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  task_id      TEXT PRIMARY KEY,
  project_id   TEXT NOT NULL,
  parent_id    TEXT,
  title        TEXT NOT NULL,
  role         TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',
  dependencies TEXT,                    -- JSON array
  scope        TEXT,                    -- JSON {allowed[], forbidden[]}
  acceptance   TEXT,                    -- JSON array
  attempts     INTEGER NOT NULL DEFAULT 0,
  tool_calls   INTEGER NOT NULL DEFAULT 0,
  interrupted  INTEGER NOT NULL DEFAULT 0,   -- 截断次数
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
  agent_id        TEXT PRIMARY KEY,
  role            TEXT NOT NULL,
  skill           TEXT,                 -- skill 名@版本
  status          TEXT NOT NULL DEFAULT 'idle',   -- idle|running|blocked|stopped
  current_task_id TEXT,
  tool_call_count INTEGER NOT NULL DEFAULT 0,
  tool_call_limit INTEGER NOT NULL DEFAULT 60,
  created_at      TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
  checkpoint_id  TEXT PRIMARY KEY,      -- chk-042-3
  task_id        TEXT NOT NULL,
  seq            INTEGER NOT NULL,      -- 对应 system.checkpoint 事件
  git_sha        TEXT,
  files_sha256   TEXT,                  -- JSON {path: hash}
  tool_calls     INTEGER,
  created_at     TEXT NOT NULL
);
```

**投影纪律**:`tasks.status / attempts / tool_calls / interrupted`、`agents.status / tool_call_count` 全部由事件流投影;`checkpoints` 表由 `system.checkpoint` 事件写入。投影失败不影响事件落库——事件库是唯一事实源,投影可随时重建。

---

## 6. 指标聚合(全部从 events 表计算)

> 定义与 validation-model §4.1 对齐;趋势比绝对值重要,跌破基线必须停下调查。

### 6.1 first_attempt_success(首试成功率)

**定义**:委派任务一次通过双验证的比例(重试/打回/换法均不算首试)。

**判定**:某任务从 `task.created` 到首次 `task.completed` 之间,若不存在 `validation.failed`,则算首试通过。

```sql
WITH completed AS (                          -- 每个任务首次 completed 的 seq
  SELECT task_id, MIN(seq) AS done_seq
  FROM events WHERE type = 'task.completed' GROUP BY task_id
),
first_fail AS (                              -- completed 之前是否发生过验证失败
  SELECT e.task_id, MIN(e.seq) AS fail_seq
  FROM events e JOIN completed c ON e.task_id = c.task_id
  WHERE e.type = 'validation.failed' AND e.seq < c.done_seq
  GROUP BY e.task_id
)
SELECT
  COUNT(c.task_id)                                              AS total,
  COUNT(c.task_id) - COUNT(f.task_id)                           AS first_attempt_ok,
  ROUND(1.0 * (COUNT(c.task_id) - COUNT(f.task_id))
        / NULLIF(COUNT(c.task_id), 0), 3)                       AS rate
FROM completed c LEFT JOIN first_fail f ON c.task_id = f.task_id;
```

按 Agent 分组时,把 `task.completed` 事件 JOIN 到该任务最近一次 `task.assigned` 的 `agent_id`。

### 6.2 path_errors(路径错误数)

**定义**:因路径问题失败的次数:文件未写入预期路径、在错误目录执行。等价于失败分类为 `path_error` 的事件计数。

```sql
SELECT COUNT(*) AS path_errors
FROM events
WHERE type = 'validation.failed'
  AND json_extract(payload, '$.failure_class') = 'path_error';

-- 兼容 validation.blocked(越权写 forbidden 路径)口径:
SELECT COUNT(*) AS path_errors
FROM events
WHERE (type = 'validation.failed'
       AND json_extract(payload, '$.failure_class') = 'path_error')
   OR type = 'validation.blocked';
```

### 6.3 human_intervention(人工介入次数)

**定义**:流程需要人类介入的次数(三挡板、第 3 次失败上报、发布授权、外部阻塞)。

```sql
SELECT COUNT(*) AS human_intervention
FROM events WHERE type LIKE 'human.%';
-- 等价口径:type IN ('human.review_requested','human.decision','human.intervention')
-- 按挡板分组:
SELECT json_extract(payload, '$.gate') AS gate, COUNT(*)
FROM events WHERE type = 'human.review_requested' GROUP BY gate;
```

### 6.4 task_truncation_rate(截断率,治理指标)

**定义**:`system.interrupted` 事件数 ÷ 任务数。

```sql
SELECT
  (SELECT COUNT(*) FROM events WHERE type = 'system.interrupted') AS interrupted,
  (SELECT COUNT(DISTINCT task_id) FROM events WHERE type = 'task.created') AS tasks,
  ROUND(1.0 * (SELECT COUNT(*) FROM events WHERE type = 'system.interrupted')
        / NULLIF((SELECT COUNT(DISTINCT task_id) FROM events
                  WHERE type = 'task.created'), 0), 3) AS truncation_rate;
```

> 指标一律**按需计算**(Dashboard 刷新 / `factory metrics` 时执行 SQL),不维护统计表——事件库即数据仓库。

---

## 7. 断点恢复(从事件流重建状态)

### 7.1 恢复流程 `restore(task_id)`

```
1. 回放       SELECT * FROM events WHERE task_id=? ORDER BY seq
              → 重建任务状态(不依赖任何对话记忆)
2. 找断点     SELECT * FROM checkpoints WHERE task_id=? ORDER BY seq DESC LIMIT 1
              → 最近 checkpoint(chk-042-3, 记录 git_sha + 文件哈希 + tool_calls)
3. 一致性校验 对比 checkpoint.files_sha256 与工作区实际文件哈希;
              git_sha 与当前 HEAD 不一致时,以实际为准,
              不盲目 checkout(实证:盲目恢复会覆盖已完成改动)
4. 决策       未完成步骤存在 → 重新委派(可复用原 Agent 或新 Agent),
              发 task.assigned(续跑语义)+ system.resumed(from_seq=断点 seq)
5. 续跑       从断点后继续执行,继续发事件;
              断点之前的动作不重放、不重复执行
```

### 7.2 一致性校验规则

| 校验项 | 通过 | 不通过处置 |
|---|---|---|
| checkpoint 文件哈希 = 实际文件哈希 | 直接续跑 | 以实际为准,重发 `system.checkpoint` 记录新哈希,再续跑 |
| checkpoint git_sha = 实际 HEAD | 直接续跑 | 不 checkout;diff 后人工确认或按实际状态续跑 |
| 任务在 checkpoint 后已有新事件 | 跳过已做步骤 | 从新事件之后续跑(增量恢复) |

### 7.3 恢复完成标志

恢复成功后必须发 `system.resumed` 事件(载荷含 `from_seq` 与 `checkpoint_ref`),保证"恢复"本身可审计、可回放。

---

## 8. 落地要点(KISS)

1. **只有一张必建表**:events;投影表可后补、可重建,别在第一天过度设计。
2. **写事件是唯一写路径**:任何状态变化 = 一条 INSERT;没有第二条写路径,恢复和审计才成立。
3. **stage/action/result/evidence 四列**承载检索与指标,**payload 兜底一切扩展**,schema 永不因新事件类型而变。
4. **指标按需算**:先跑通 SQL 再考虑物化;数据量大了再上定时聚合表。
5. **证据引用不存大对象**:events 只存 `ref://`,产物留在 artifacts/,防库膨胀。
