# ADR-0015 — Phase 5B: Metrics Intelligence Layer (工厂指标层)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 5B 要求从事件和状态生成生产指标 (只读): FactoryMetrics 六域 (tasks/
executions/agents/workflows/validation/failures), 含 first_attempt_success_rate 与
failure_reason_count; CLI `factory metrics` (+ `--json`) + Dashboard Metrics View;
Event `metrics.viewed`。设计文档 phase5b-status.md 明确 **Metrics 只读** — 禁止 AI 分析
/ML/自动优化/修改任务与 Agent 状态。

仓库现状: 已有 dashboard 层的 FactorySnapshot 聚合 (4C-4) 与 events/metrics.py
任务口径小助手 (早期 Phase)。本 ADR 界定指标层与这两者的关系, 避免口径打架。

## 决策

### 1. 只读铁律: 收集器纯读, 事件由命令层发

MetricsCollector 只调用各 store/registry 的**读接口** (query/list/count), 不调用
任何写方法, 不发任何事件 (模块解耦, 同 DashboardCollector 模式)。唯一副作用
metrics.viewed 审计事件由 CLI 命令层 cmd_metrics 经 EventLogger 发出 (ADR-0002:
所有 CLI 行为必须产生 Event, 同 dashboard.viewed)。collect 无副作用 → 重复调用
结果仅 generated_at 不同, 聚合值确定。

### 2. 指标默认纯计算不持久化; MetricsStore 为可选快照出口

指标一律按需从 store/事件聚合, 不维护统计表 (event-model §6 按需聚合)。metrics/
store.py 的 MetricsStore 是**可选**快照持久化 (FactoryMetrics → JSON 原子写, 损坏抛
CorruptMetricsStoreError), 仅供调试对比/外部消费/CI 归档 — CLI 与 Dashboard 均不
依赖 (KISS)。

### 3. 六域口径统一 (与既有口径并存, 不强行统一)

- **Task**: total = TaskStore 任务数; completed = DONE 数; failed = 有 task.fail
  事件的 distinct 任务数 (**TaskStatus 无 FAILED 态, 失败只能从事件观测**);
  success_rate = completed / (completed + failed), 无终态 0.0。
- **Execution**: total/success/failed = 请求状态 SUCCESS/FAILED 数 (请求状态为
  权威); first_attempt_success_rate 见决策 4。
- **Agent**: agents = {agent_id: AgentMetric}, assignment_count/success_count/
  failed_count/success_rate 来自 agent.assignment.* 事件 (注册表兜底 0; 事件中
  出现的未注册 agent_id 也纳入); agents_total = 注册 Agent 数。
- **Workflow**: run_count = 运行实例数; success_rate = completed / run_count
  (**全部运行实例, 同 dashboard 执行口径, 未完成运行计入分母**) — 与
  events/metrics.py 任务口径 (success/(success+fail)) 并存, 不统一 (precedent:
  ADR-0012 决策 4)。
- **Validation**: total_rules = validation.rule.completed 数, PASS/FAIL/SKIP/ERROR
  按结果列聚合 (**单次验证每规则一条, 无重复计数**); pass_rate = PASS / total_rules
  (含 SKIP/ERROR 分母); runs/failed_runs = validation.completed/failed 事件数。
- **Failure**: failure_reason_count = task.fail 失败原因直方图, 归类键 payload.stage
  优先, 回落 payload.error, 再回落 "unknown"; 次数降序输出。stage 是有界类别
  (架构/开发/测试/运行等), 比自由文本 error 更适合作直方图键。

### 4. first_attempt_success_rate: 每任务最早执行, 未终态不进分母

每任务取**最早执行** (created_at 排序, id 决胜), 在已到达终态 (SUCCESS/FAILED) 的
任务中, 首次执行即 SUCCESS 的比例; 无则 0.0。**未终态 (PENDING/RUNNING) 的首次
执行不进分母** — 尚未分出成败, 不应拉低比率。例: 首次 FAILED 重试 SUCCESS →
整体成功率 0.5, 但首次执行即 FAILED → first_attempt_success_rate 0.0 (与整体
成功率形成对照, 语义独立)。

### 5. 事件扩展: metrics.viewed

扩 str-Enum EventType 成员 `METRICS_VIEWED = "metrics.viewed"` (纯增量, type 列存
字符串, 不改表 — ADR-0001 路径)。payload 含六域指标计数汇总 (tasks_total/
tasks_completed/tasks_failed/executions_total/executions_success/executions_failed/
first_attempt_success_rate/agents_total/workflow_runs/workflow_success_rate/
validation_pass_rate/failure_reasons), 只读不写任何状态。

### 6. 渲染为纯文本 (无 ANSI), 纯函数共用

metrics/reports.py 的 format_metrics 是「FactoryMetrics → str」纯函数, CLI
_print_metrics 与测试共用; 输出无转义码, 管道/CI/测试断言安全。表格对齐复用
cli/main.py _render_table 同款算法 (KISS, 标准库零依赖)。

### 7. Dashboard 集成: 第八视图 + 快照内嵌

dashboard VIEWS 增 "metrics" 视图 (views.build_metrics), 九元组
(overview/tasks/agents/workflows/executions/recovery/catalog/metrics) —
既有精确集合断言数学上必然失败, 最小化更新测试; FactorySnapshot 增
factory_metrics: FactoryMetrics 字段, DashboardCollector 复用 MetricsCollector
装配。dashboard.viewed 与 metrics.viewed 各自独立审计。

## 验证

- pytest 1395 全绿 (1335 + 60 metrics 新增, 2 处收尾修复)
- 收尾修复 (均为测试期望, 实现语义正确):
  1. test_executions_from_runtime_store: 原构造 "EX-001 SUCCESS + EX-002 FAILED"
     中 T-001 最早执行即 EX-001 (created_at, id 决胜) = SUCCESS → 实现 1.0,
     期望 0.5 错; 改为 "首次 FAILED 重试 SUCCESS" 场景 (EX-001 FAILED +
     EX-002 SUCCESS → rate 0.0), 更贴合决策 4 语义。
  2. test_repeated_collect_deterministic: generated_at 每次 collect 是新时间戳,
     确定性只对聚合值成立; 测试排除 generated_at 后比较。
- 冒烟: factory metrics / factory metrics --json / factory dashboard --view
  metrics 均正常 (metrics.viewed 事件落库)。
