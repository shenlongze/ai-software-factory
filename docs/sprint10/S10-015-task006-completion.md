# S10-015 Task 006 Completion Report — AI Factory Dashboard

> 日期: 2026-08-12 | 状态: 完成 (待人工审核) | 范围: AI Software Company Control Center
> 关联: docs/design/AF-UI-Architecture.md §7 / S10-015-architecture-review.md

---

## 1. 实现内容

```
Dashboard Adapter (toDashboardViewModel):
  组合 dashboard 七域 + 每项目 workflow/timeline/backlog → DashboardViewModel
  (projects / runningAgents / workflowStatus / blockedTasks / recentEvents / qualitySummary)

AfDashboard 组件 — 6 模块 (Control Center):
  ① Active Projects     复用 AfProjectCard (真实项目 + workflow 状态)
  ② Running AI Employees Agent 卡 (名称/当前任务/Workflow Stage/状态)
  ③ Workflow Status     真实实例阶段链 (项目 + 阶段状态 + 当前阶段)
  ④ Blocked Tasks       任务名/原因/负责人/下一步
  ⑤ Recent Runtime Events 复用 AfTimeline (倒序, 最近 N 条)
  ⑥ Quality Summary     Tests/Quality Gate/Build (无数据 → Unavailable)

路由: #/workspace (dashboard) → AfDashboard; #/workspace/projects → 项目列表保留
```

## 2. Dashboard 架构说明

```
                Dashboard UI (AfDashboard 6 模块)
                    ↑
            Dashboard Adapter (toDashboardViewModel)
                    ↑
   dashboard 七域 + projects + workflow + timeline + backlog (真实 API)
```

## 3. 数据来源说明

| 模块 | 数据源 | 真实 |
|---|---|---|
| Active Projects | GET /api/dashboard.projects | ✅ markpad + ScorePocket |
| Running Employees | dashboard.agents (status 过滤) | ✅ 3 Agent AVAILABLE → 诚实空态 |
| Workflow Status | project.workflow_id → GET workflow 实例 | ✅ ScorePocket failed 链 |
| Blocked Tasks | backlog tasks status=blocked | ✅ 无 → 空态 |
| Recent Events | per-project timeline + activity | ✅ 真实失败事件 |
| Quality Summary | cost/approvals/experience | ✅ 8 calls 13% + 1 待审批 + Unavailable |

## 4. Adapter 设计

```
toDashboardViewModel(dashboard, extras) 纯函数:
  projects:      dashboard.projects → toWorkspaceProject (复用)
  runningAgents: agents status→running (RUNNING/EXECUTING/WORKING) → RunningAgent
                 (workflowStage 从运行中阶段 role 匹配; 无 → null 不编造)
  workflowStatus: 有真实实例项目 → toWorkflowPipeline 阶段链 (无实例不编造)
  blockedTasks:   backlog blocked task (dependency→标题翻译, assignee→人话)
  recentEvents:   timeline + activity 合并倒序, 上限 10
  qualitySummary: cost.calls>0→Tests; approvals pending→QualityGate;
                  experience.total>0→Build; 无 → undefined (UI Unavailable)
缺失 → 空/Unavailable, 不崩溃 (§6.3 降级)
```

## 5. UI 模块说明 (浏览器实测 #/workspace)

```
AI 软件公司控制中心 — 全部来自真实后端数据
① markpad (活跃/未启动/0%) + ScorePocket (想法/失败/development/待办2 失败1)
② 暂无执行中 AI 员工            ← 诚实 (3 Agent AVAILABLE)
③ ScorePocket 失败 → 开发[失败] → 测试[待办] → 发布[待办]
④ (无阻塞任务)
⑤ 工作流失败: DeveloperError: provider response contains no parseable...
⑥ Tests: 执行 8 次 · 成功率 13% | Quality Gate: 待审批 1 项 (PRD) | Build: Unavailable
```

## 6. 测试结果

```
前端 vitest:  636 passed (53 files) — 含新增:
  dashboard-adapter.test.ts  (12 测试: 映射/AVAILABLE 空态/activity 空/降级)
  af-dashboard.test.tsx      (15 测试: 6 模块/诚实空态/Unavailable/点击跳转)
tsc:          0 error
build:        ✓ (307KB JS)
后端 pytest:  7507 passed (零影响)
```

## 7. 限制和后续规划

```
限制:
1. Running AI Employees 当前诚实空态 (3 Agent 均 AVAILABLE) — 待真实执行时显示
2. Quality Summary Build 显示 Unavailable (后端无 build 数据) — 不编造
3. recentEvents 上限 10 条 (RECENT_EVENTS_LIMIT)
后续:
- Agent 真实执行时 Dashboard 自动显示 (无需改动, Adapter 已就绪)
- 点击 Project/Task 已接跳转 (→ #/project/{id} / todo / workflow)
```

## Commit

```
9573805  feat(S10-015): implement AI Factory dashboard (Control Center — 6 模块 + Dashboard Adapter + 真实数据 + 诚实空态)
```

## 用户流程验收

```
✅ 打开 AI Factory → #/workspace → 真实 Dashboard (Control Center)
✅ 真实 Project (markpad + ScorePocket)
✅ Workflow 状态 (ScorePocket 失败链)
✅ Agent 状态 (诚实: 暂无执行中)
✅ 点击项目 → #/project/{id} → Task Detail / Workflow / Runtime (既有闭环)
```

---

> 状态: 完成 | 下一步: 等待人工审核 (Task 007 Quality Gate / S10-016 不自动进入)
