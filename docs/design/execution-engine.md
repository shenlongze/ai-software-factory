# Execution Engine (S10-011 设计)

> 状态: 架构待确认 | 范围: 设计文档 (不开发 UI)
> 解决: 谁来做? 什么时候做? 能不能同时做? 如何避免错误执行?

## 一、四层模型

```
Project
├── Planning Layer     (做什么/为什么/先做什么)
│   ├── Roadmap / Backlog / Sprint / Task / Priority / Dependency
│
├── Decision Layer     (AI 决策支持)
│   ├── Priority Engine / Critical Path / Dependency Analyzer
│
├── Execution Layer    (谁来做/什么时候做)
│   ├── Auto Execution (Scheduler/Dispatcher/Parallel Controller/Agent Runner)
│   ├── Manual Execution (Execute Now + Pre-condition Check)
│   └── Condition Checker
│
└── Monitoring Layer   (做得怎么样)
    ├── Runtime / Logs / Progress / Risk / Notification
```

## 二、Auto Mode (默认)

```
Sprint Ready → Task Analysis → Priority Sort → Dependency Check
  → Find Available Tasks → Assign Agent → Execute → Review → Next Task
```

AI Project Manager 自动计算 Next Actions:
```
输入: Task + Priority + Dependency + Milestone + Agent Capability + Current Runtime
输出: 可执行任务列表 (满足依赖 + 有可用 Agent) → 自动启动
```

## 三、并行执行规则

```
每个 Task: depends_on / resource / conflict_scope

可以并行: 无文件冲突 + 无数据冲突 + 无模块依赖
不能并行: 冲突 (如 修改数据库结构 vs 生成迁移脚本) → Sequential

默认 Max Parallel Tasks: 5 (Project Setting)
配置层级: Global → Workspace → Project → Sprint
```

## 四、Agent Dispatcher

```
Task → Requirement Analysis → Required Skill → Find Agent → Assign
例: 优化数据库查询 → Skill: SQL Optimization → Agent: Backend Expert Agent
```

## 五、Manual Mode

```
用户点击 [Execute] → Pre-condition Check:
  1. Dependency 2. Required Files 3. Required Agent 4. Environment 5. Previous Task Status
不满足 → 明确拒绝 (如 "前置任务未完成: ❌ 自动化测试 TASK-089 RUNNING")
满足 → [Confirm] 执行
```

## 六、Task 状态机 (执行侧)

```
BACKLOG → READY → WAITING_DEPENDENCY → AVAILABLE → ASSIGNED
  → RUNNING → REVIEW → TESTING → DONE
异常: BLOCKED / FAILED / CANCELLED
```

## 七、Notification Engine (AI 主动提醒)

```
优先级变化: "⚠️ T001 重要性提升 — 影响 Release Milestone — 建议 P2→P1"
阻塞: "🚨 项目风险 — TASK-023 延迟 — Sprint 延期 3 天 — 建议增加 Agent"
下一步: "✅ 当前任务完成 — 推荐 TASK-034 (预计 2h) — [执行] [查看]"
```

## 八、绑定与隔离

```
所有 Agent 执行绑定: project_id + sprint_id + task_id
runtime/ 保存执行过程 (agent-execution/skill-execution/mcp-calls/workflow-instances/state/context)
management/ 保存业务状态 (roadmap/backlog/sprint/task/risk/metrics)
禁止: 项目管理状态存储到 runtime; 跨项目运行时污染
```

## 九、数据流

```
Workflow Instance: Input → Agent Chain → Tool Execution → Output → Review → Next Step
绑定: workflow_ref (software-development-v1) + parameters (industry) + agents + skills + mcps
```

## 十、实施依赖

```
前置: Project Lifecycle (S10-009) + Project Management (S10-010) 数据模型
本引擎作为 S10-011 — 依赖 S10-009/010 落地后实施
```
