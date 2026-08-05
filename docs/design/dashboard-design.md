# AI Software Factory — Dashboard 设计

> 版本: v1.0 | 状态: 设计稿
> 关联文档: [runtime-design](./design/runtime-design.md)、[event-model](./event-model.md)、[cli-design](./cli-design.md)、[validation-model](./design/validation-model.md)
> 技术栈: Rich(CLI 实时)/ Markdown(状态文件),第一版不做 Web
> 设计原则: 只读投影、一个页面回答六个问题(在做什么/每任务什么状态/谁在做/卡在哪/进展如何/下一步)、KISS。

---

## 1. 设计约束

1. **只读投影**:Dashboard 不写任何状态,所有数据来自 events 表查询(见 event-model.md);崩溃/重启后重放事件即可重建。
2. **无状态渲染**:每个视图都是"查询函数 + 渲染函数",输入 events 表,输出表格;不做事件订阅缓存(第一版查询成本足够低)。
3. **两个出口,同一数据源**:
   - CLI Dashboard:Rich 实时表格,人盯屏用;
   - Markdown Dashboard:自动生成状态文件,提交进仓库 / CI 用 / 复盘用。
4. **颜色语义**(CLI):`done/ok`=绿,`running/verifying`=绿/黄,`blocked/failed`=红,风险标记=黄。

---

## 2. 四视图规格

> 每个字段标注数据来源(事件类型 + 聚合方式);查询默认按 `project_id` 过滤,`seq` 升序。

### 视图 1:Project 总览(overview)

| 列/行 | 说明 | 数据来源(events 表) |
|---|---|---|
| Project / Workflow / Repo | 项目名、绑定流程、仓库 | `projects` 投影表 |
| Active Tasks | 进行中任务数 | `COUNT(task.assigned)` − `COUNT(task.completed)` − `COUNT(task.cancelled)`(按 project,取全量) |
| Blocked Tasks | 阻塞任务数 | `task.blocked` 且其后无 `task.resumed` / `task.cancelled` |
| Agents Running | 运行中 Agent 数 | `COUNT(agent.started)` − `COUNT(agent.stopped)` |
| 里程碑进度 | M1 完成度 | 关联任务的 `task.completed` / `task.created` 计数比 |
| 质量指标 | first_attempt_success / path_errors / human_intervention / 截断率 | 事件聚合(event-model §6 的 SQL) |
| 最近事件 | 最新 10 条 | `SELECT * FROM events WHERE project_id=? ORDER BY seq DESC LIMIT 10` |

### 视图 2:Task 列表(tasks,每任务一行)

| 列 | 说明 | 数据来源 |
|---|---|---|
| Task ID / 标题 | 定义性数据 | `tasks` 投影表(`task.created` 写入) |
| 状态 | pending/assigned/running/verifying/done/blocked/failed | 投影:该任务最新 `task.*` 事件的 `stage` |
| 角色 | dev/test/debugger/… | `task.created` payload.role |
| 进度 | 已完成步骤/总步骤 | `checkpoints` 数(按 seq)/ 流程步骤数(`system.checkpoint` 事件计数) |
| 当前动作 | 最新动作简述 | 最新 `agent.action` 的 `action` 列 |
| 上次事件 | 类型 + 时间 | `MAX(seq)` 事件 |
| 下一步 | 状态机推导 | workflow 定义 + 当前状态(如 verifying → "等待验证";blocked → "等待 PO 决策") |
| 风险标记 | 截断/多次失败/越权 | `system.interrupted` ≥ 阈值;`validation.failed` ≥ 2;`validation.blocked` > 0 |

### 视图 3:Agent 面板(agents)

| 列 | 说明 | 数据来源 |
|---|---|---|
| Agent ID / 角色 | 实例身份 | `agents` 投影表(`agent.started` 写入) |
| 当前任务 | 正在执行的任务 | 投影:最新 `agent.started`(未 `agent.stopped`)的 task_id |
| 当前动作 | 实时动作 | 最新 `agent.action` 的 `action` 列 |
| 工具调用数/上限 | 防截断预警 | `system.metric`(key=tool_calls)最新值 / `agent.started` payload.tool_call_limit;接近上限(≥80%)标黄 |
| 历史指标 | 该 Agent 首试成功率/路径错误 | 该 agent 关联任务的事件聚合(event-model §6.1 按 agent 分组、§6.2) |

### 视图 4:Event 时间线(timeline,回放视图)

| 列 | 说明 | 数据来源 |
|---|---|---|
| seq / 时间 / 类型 | 原始事件 | events 表按 seq 升序 |
| task / agent | 归属 | events.task_id / events.agent_id |
| stage / action / result | 语义列 | events 表四列 |
| evidence | 证据跳转 | events.evidence(`ref://`) |

用途:截断续跑定位、挡板原因追溯、审计。支持过滤(`--type validation.failed --task T-042`)与**跳转到 checkpoint**:`--at chk-042-3` 显示该断点之前的快照(对应视图 2 的历史状态)。

---

## 3. CLI Dashboard(Rich 实时)

### 3.1 命令与参数

```bash
factory dashboard [--watch 2] [--view overview|tasks|agents|timeline] [--project P-markpad]
```

- `--watch N`:每 N 秒刷新(默认 2;不带 `--watch` 输出一次即退出,适合脚本)。
- `--view`:只渲染单视图;缺省四视图同屏(Layout 见下)。
- 非 TTY(管道/CI)时自动退化为单次输出,避免刷屏。

### 3.2 布局(Rich Layout)

```
┌──────────────────────────────────────────────────────────┐
│ ① Project 总览  P-markpad   Active 3  Blocked 1  Agents 2│  ← Panel(总览)
├──────────────────────────────────┬───────────────────────┤
│ ② Task 列表(Rich Table)          │ ③ Agent 面板(Table)   │
│  T-042 assigned dev  撤销/重做    │  A-012 dev   T-042    │
│  T-041 running  debugger 光标偏移  │  A-013 debugger T-041 │
│  …                                │  …                   │
├──────────────────────────────────┴───────────────────────┤
│ ④ Event 时间线(最近 8 条,倒序)                            │
│  1090 10:32 validation.failed T-042 FAIL ref://val-3.log │
│  …                                                       │
└──────────────────────────────────────────────────────────┘
```

- 用 `Layout` 分区 + `Live` 包裹:每次刷新重跑 4 个查询函数,`live.update()` 整屏替换(1–2s 批量刷新,不做逐事件闪烁)。
- 顶部 Panel 附质量指标一行:`first_attempt_success 0.92 | path_errors 1 | human_intervention 0 | 截断率 0.05`。
- Task 表风险标记列:命中条件即显示 ⚠ 并整行标黄。
- 终端宽度不足时(检测 `os.get_terminal_size`):自动隐藏"当前动作"列、时间线只留 4 条。

### 3.3 查询实现(全部只读)

```python
# 伪代码:每个视图 = 一个纯查询函数,输出给 Rich 组件
def overview_rows(project_id):   # → Panel 内容
    active  = count('task.assigned') - count('task.completed') - count('task.cancelled')
    blocked = count('task.blocked') - count('task.resumed') - count('task.cancelled')
    ...
def task_rows(project_id):       # → Table(视图 2 字段,join tasks 投影表)
def agent_rows(project_id):      # → Table(视图 3 字段,join agents 投影表)
def timeline_rows(project_id, n=8):  # → Table(视图 4,按 seq 倒序)
```

刷新循环:`while True: rows = [f(project_id) for f in (overview, tasks, agents, timeline)]; live.update(render(rows)); sleep(watch)`;Ctrl-C 退出码 130。

---

## 4. Markdown Dashboard(状态文件)

### 4.1 命令

```bash
factory dashboard --format markdown --out docs/STATUS.md [--project P-markpad]
```

- 生成后**提交进仓库**,天然获得版本化状态历史;CI 可 `git diff` 检测状态变化(如状态文件 diff 出现 blocked → 告警)。
- 与 CLI 同源:同一组查询函数,只是渲染器不同(Rich → 字符串模板)。

### 4.2 生成示例

```markdown
# Factory 状态 — P-markpad

> 更新于 2026-08-05T10:35:00Z | 数据源: events 表(seq ≤ 1090)

## 总览
| 指标 | 值 |
|---|---|
| Active Tasks | 3 |
| Blocked Tasks | 1 |
| Agents Running | 2 |
| 里程碑 M1 | 2/5 (40%) |
| first_attempt_success | 0.92 |
| path_errors | 1 |
| human_intervention | 0 |
| 截断率 | 0.05 |

## 任务列表
| Task | 状态 | 角色 | 标题 | 当前动作 | 下一步 | 风险 |
|---|---|---|---|---|---|---|
| T-042 | assigned | dev | 撤销/重做 | 等待委派执行 | 等待验证 |  |
| T-041 | blocked | debugger | 光标偏移调查 | run_repro | **等待 PO 决策 (G2)** | ⚠ |
| T-038 | done | dev | 事件分发 | — | — |  |

## Agent
| Agent | 角色 | 当前任务 | 工具调用 | 首试成功率 |
|---|---|---|---|---|
| A-012 | dev | T-042 | 12/60 | 0.80 |
| A-013 | debugger | T-041 | 47/60 ⚠ | 1.00 |

## 最近事件
| seq | 时间 | 类型 | task | action | result |
|---|---|---|---|---|---|
| 1090 | 10:32:10 | validation.failed | T-042 | independent verify L2 | FAIL |
| 1088 | 10:31:44 | task.reported | T-042 | self-report | PASS |
| … | | | | | |
```

### 4.3 使用场景

| 场景 | 用法 |
|---|---|
| 盯屏 | `factory dashboard --watch 2`(终端) |
| 每日复盘 | `factory dashboard --format markdown --out docs/STATUS.md`,提交留痕 |
| CI 守卫 | 定时生成 + `git diff --exit-code` 检测状态突变;`grep 'blocked'` 告警 |
| 截断续跑 | `factory dashboard --view timeline --at chk-042-3` 定位断点 |
| 指标汇报 | `factory metrics --period 7d`(视图 1 质量指标行的独立命令) |

---

## 5. 字段 → 事件来源映射(总表)

| 视图字段 | 来源事件 |
|---|---|
| Active Tasks | `task.assigned` − `task.completed` − `task.cancelled` 计数 |
| Blocked Tasks | `task.blocked` 未 `task.resumed`/`task.cancelled` |
| Agents Running | `agent.started` − `agent.stopped` 计数 |
| 里程碑进度 | 关联任务 `task.completed` / `task.created` |
| first_attempt_success | `task.completed` + 其前 `validation.failed`(event-model §6.1) |
| path_errors | `validation.failed`(failure_class=path_error)+ `validation.blocked` |
| human_intervention | `human.*` 计数 |
| 截断率 | `system.interrupted` / `task.created` |
| 任务状态 | 最新 `task.*` 的 `stage` |
| 任务当前动作 | 最新 `agent.action` 的 `action` |
| 任务进度 | `system.checkpoint` 计数 / 步骤总数 |
| 任务风险标记 | `system.interrupted`、`validation.failed`(≥2)、`validation.blocked` 计数 |
| Agent 当前任务 | 最新 `agent.started`(未 `agent.stopped`) |
| Agent 工具调用 | `system.metric`(key=tool_calls)最新值 |
| Agent 历史指标 | 该 agent 任务集合的聚合(§6.1/§6.2) |
| 时间线 / 最近事件 | events 表按 seq |

---

## 6. 落地要点(KISS)

1. **先做 CLI 版**:Rich 四视图同屏 + `--watch`,一天可交付;Markdown 只是换渲染器,半小时。
2. **查询函数共享**:CLI / Markdown / `factory metrics` 用同一组 events 查询函数,保证三个出口数据一致。
3. **别建缓存表**:第一版每次刷新直查 events(万级事件 SQLite 毫秒级);数据量大再考虑物化投影。
4. **Web 版后置**:等 CLI/Markdown 形态跑顺、确认字段有用后,再包一层 HTTP(查询函数原样复用)。
5. **Dashboard 不写状态**:所有按钮/操作(恢复、批准)一律走 CLI 命令发事件,Dashboard 只负责展示。
