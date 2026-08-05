# ADR-0012 — Phase 4C-4: Dashboard (只读控制台)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 1-4C-3 已有完整事件审计与全 store (Task/Agent/Workflow/Runtime/Checkpoint),
但缺少"一眼看清工厂在做什么"的只读控制台。CLI 各子命令分散, 计数无汇总视图。
需求: `factory dashboard` — Rich 渲染的六视图总览 (Overview/Tasks/Agents/Workflows/
Executions/Recovery) + `--json` 结构化输出, 供盯屏与脚本消费 (phase4c4-status.md)。

## 决策

### 1. 只读投影: Dashboard 不写任何状态

`DashboardCollector` 只调用各 store/registry 的读接口 (list/get/count/query),
聚合为 `FactorySnapshot` (查询时刻投影, Pydantic v2)。聚合期间零写操作:
不修改 Task/Agent/Workflow/Execution/Event, 不建缓存表 (dashboard-design.md §6.3)。
崩溃/重启后重查即可重建 (同 event-model §6 按需聚合原则)。

### 2. 快照 = 汇总计数 + 明细 items 同一数据源

每个子模型同时携带 `by_status` 等汇总与 `items` (JSON 友好 dict): Rich 渲染器与
`--json` 输出消费同一 `FactorySnapshot`, 保证两个出口数据一致 (dashboard-design.md
§6.2 查询函数共享)。空工厂: 全字段默认值, collect 永不抛错。

### 3. 六视图而非设计稿四视图

dashboard-design.md §2 的四视图 (总览/Task/Agent/时间线) 落地为六视图
(Overview/Tasks/Agents/Workflows/Executions/Recovery, phase4c4-status.md 范围):
Workflows/Executions/Recovery 拆为独立视图, 直接对应各自 store 的读接口
(WorkflowStore/RuntimeStore/CheckpointStore), 时间线并入 Overview (Recent Events)。

### 4. Metrics 从 store 计数与事件聚合, 不建统计表

- success rate = executions SUCCESS / 全部执行 (含未完成), 无执行时 0.0
  (phase4c4-status.md §Metrics 口径, 区别于 events/metrics.py 的
  success/(success+fail) 任务口径 — 两者服务不同域, 并存不冲突)。
- failure count = executions FAILED 数。
- validation summary = `validation.rule.completed` 结果列聚合
  (PASS/FAIL/SKIP/ERROR 粒度数据, 单次验证每规则一条, 无重复计数)。

### 5. dashboard.viewed 事件 (Event Audit)

`factory dashboard` 唯一副作用是经 EventLogger 发 `dashboard.viewed` (ADR-0002:
所有 CLI 行为必须产生 Event); 载荷含 view 与各域计数汇总。收集器自身不发事件
(模块解耦 — 只读查询与审计分离)。

### 6. 渲染器纯函数 + 纯文本出口

`DashboardRenderer.render(snapshot)` 返回无 ANSI 的纯文本 (Console.export_text):
管道/CI/测试断言安全; TTY 下由 Rich 自动着色 (颜色语义 dashboard-design.md §1.4:
done=绿, running=黄, failed=红)。`--watch` 实时刷新延后 (非本阶段范围, KISS)。

## 验证

- pytest 全绿 (1103 已有 + dashboard 新增 ≥50: 模型/收集器/渲染器/Metrics/CLI/事件/只读性)
- CLI 冒烟: 构造 task/agent/workflow/execution/checkpoint 数据 →
  `factory dashboard` 六视图输出 + `--json` 快照 → `dashboard.viewed` 入事件库
