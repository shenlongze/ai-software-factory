# ADR-0017 — Phase 6B: Workspace Operations Dashboard (Workspace 运营视图)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 6B 在 Phase 6A (workspace 层) 之上加 Workspace 级**聚合展示**: `factory
dashboard --workspace` (Workspace Summary 六面板) / `factory metrics --workspace`
(项目对比表) / `factory event logs --workspace` (跨项目事件时间线) + Agent
Utilization / Runtime Usage 运营视图 + workspace.dashboard/metrics/events.viewed
审计事件。设计文档 phase6b-status.md 明令 **只做聚合展示, 不改 Task/Execution/
Runtime/Metrics 核心流程** (禁止), 新增测试 ≥70 (1498 不回归)。

仓库现状: dashboard 层已有 FactorySnapshot 聚合 (ADR-0012) 与 Projects View
(ADR-0016); metrics 层已有 FactoryMetrics 六域 (ADR-0015)。本 ADR 界定 workspace
聚合与这两者的关系 — 复用不复制, 并记录收尾修复的契约裁定 (幻影项目泄漏)。

## 决策

### 1. 复用不复制: 项目对比 = 每项目 MetricsCollector, 运营视图 = 纯函数

- `metrics/workspace.py` 的 `WorkspaceCollector.comparison(project_ids)` 对每个
  项目跑 `MetricsCollector(project_id=X).collect()` (六域口径全继承 ADR-0015
  决策 3), 再抽取 `ProjectComparisonRow` 字段; 汇总行 = 全局 collect
  (project_id=None), project 标记 `"*"` (totals 行, Pydantic 默认值用
  `Field(default_factory=lambda: ProjectComparisonRow(project="*"))`)。
- Agent Utilization / Runtime Usage 写成**纯函数** `collect_agent_utilization
  (events, tasks, agents)` / `collect_runtime_usage(requests, tasks)` — 输入序列化
  数据 (models/事件), 不碰 store, 单测直接构造输入 (同 metrics/calculators.py)。
- DashboardCollector 只加默认关闭开关 `include_workspace: bool = False`:
  默认 False 时既有 dashboard 行为/成本完全不变 (新字段落 default_factory 空模型);
  True 时内部装配 WorkspaceCollector 填充 agent_utilization/runtime_usage。
  昂贵聚合一律默认关闭, 按需开启。

### 2. 项目归属铁律: 无 project 字段的记录一律 task_id → task.project

ExecutionRequest / WorkflowRun / agent.assignment.* 事件 **无 project 字段** —
聚合时一律 `task_id → task.project` 映射归属 (TaskStore.list() 建 map); 无对应
任务的孤儿记录/孤儿事件**不归属** (KISS, 无法判定项目)。注意: events 表有
project_id 列, 但 allocator._emit 发 assignment 事件**不填 project_id** — 按
e.project_id 过滤会漏掉全部分配事件, 跨项目 agent 统计必须走 task_id 映射。
推论: 零 assignment 事件的已注册 Agent 无法归属任何项目 (projects 为空) —
Agent 定义本身无项目维度 (恒为全局)。

### 3. include_workspace 装配: CLI 按标志/视图自动启用

CLI 装配 `include_workspace = workspace or view in workspace_views`, 其中
`workspace_views = {workspace, agents_utilization, runtime_usage,
workspace_events}` — `--view` 单独指定 workspace 专属视图时自动启用聚合
(数据完整), 但审计事件类型仍按 `--workspace` 标志区分 (决策 4)。collector
默认关闭 (决策 1), 既有 `dashboard` (无标志) 行为不变。

### 4. 审计事件按 --workspace 标志区分, 只读铁律不变

- `dashboard --workspace` → `workspace.dashboard.viewed`; `dashboard --view
  workspace` (无标志) → `dashboard.viewed` (只读审计按标志区分, 与渲染启用
  解耦)。`metrics --workspace` → `workspace.metrics.viewed`; `event logs
  --workspace` → `workspace.events.viewed`。
- 纯增量加 EventType 成员 (ADR-0001 路径, type 列存字符串不改表); payload 含
  全局聚合口径计数 (projects_total/tasks_total/executions_total/...)。命令唯一
  副作用 = 审计事件 (ADR-0002), 业务状态零修改 (只读铁律同 ADR-0012/0015)。

### 5. --view 默认改 None, 命令层归一化

`view = args.view or ("workspace" if workspace else "all")` — 区分「用户没传」
与「显式传 all」; 命令层返回归一化值 (JSON `data["view"] == "workspace"`),
既有测试断言 `data["view"] == "all"` 不受影响。`--workspace` 为 store_true
标志, 子解析器 default=False 即可 (无同名全局选项, 不触发 argparse
_SubParsersAction 拷贝回写覆盖, 无需 SUPPRESS)。

### 6. 无 workspace.yaml 的项目集兜底 (收尾修复: 禁自动发现泄漏)

无 workspace.yaml / 配置损坏 → 读命令兜底: dashboard 项目列表**空** /
metrics project_ids **缺省推导** (任务 project 值 ∪ 事件 project_id 值),
永不因 workspace 配置问题失败。实现用 `WorkspaceManager.load_workspace()`
(缺失 → WorkspaceNotFoundError, 损坏 → WorkspaceConfigError, 均被 CLI 捕获
转空/None), **不用 `list_projects()`** — 后者在无 workspace.yaml 时自动发现
(managed ∪ examples, ADR-0016 决策 3 的 Phase 5A 兼容语义), 会把内置示例项目
(markpad) 泄漏进 workspace 聚合: 空工厂 projects_total=1、审计 payload 虚报、
对比表出现零数据示例行, 违背「workspace 项目定义」语义与 CLI docstring
(无 workspace → 空列表)。有 workspace.yaml 时两路径等价 (load_workspace 解析
注册列表), 行为不变。

### 7. 测试冲突消解 (数学上必然失败, 最小化更新)

- **VIEWS 精确集合断言**: `set(VIEWS) == {...}` 随视图扩展必然失败
  (Phase 6B: 8 → 13, 新增 workspace/projects/agents_utilization/runtime_usage/
  workspace_events; projects 为 6A 新增) — 行为观察点非 API, 最小化更新测试
  (同 ADR-0014/0015 先例)。
- **Agent Utilization projects 断言**: 测试曾期望零分配 Agent 归属 P-alpha —
  与 `assignments == 0` 自相矛盾 (无 assignment 事件无法 task_id → project
  归属, 决策 2); 实现输出 projects=[] 正确, 修断言 (视图输出为准)。
- 既有 dashboard.viewed payload 断言只查旧键存在 — 新增键
  (workspace/agents_utilized/runtimes_used) 不破坏, 保留全部旧键。

## 验证

- pytest **1616 全绿** (1606 既有 + 10 收尾修复; Phase 6B 新增 36 workspace CLI
  测试 + workspace dashboard views / metrics 聚合对比测试)。
- 收尾修复 2 项:
  1. **实现 bug** (CLI 装配): cmd_dashboard / _cmd_metrics_workspace 改
     `load_workspace().projects` — 无 workspace.yaml 不再把自动发现的示例项目
     (markpad) 带进 projects 列表 / project_ids 推导 (决策 6); 修复 7 个失败
     (empty 渲染 "(no projects)"、projects_total 计数、审计 payload、大工作区
     30/31 计数)。
  2. **测试期望错** (决策 2 推论): zero-assignment Agent 的 projects 应为空,
     修断言。
- 冒烟: 多项目数据 → `factory dashboard --workspace` / `factory metrics
  --workspace` / `factory event logs --workspace` 均正常输出 (项目对比行、
  汇总行 "*"、跨项目事件时间线), 审计事件 workspace.*.viewed 落库。
