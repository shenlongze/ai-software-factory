# S10-057 — Team Production Validation 设计

> 日期:2026-08-15 | Sprint: S10-057 | 7 大模块设计
> 目标: 让 AI Factory 第一次真实运行完整多 Agent 软件项目

---

## 1. 架构(Team mode 增强, 单 Agent 兼容)

```
Product → Engineering Plan → Team Assignment (required_role)
    ↓
Dependency Resolution (拓扑)
    ↓
Workspace Context 注入 (project/completed/artifacts/messages/decisions)
    ↓
Agent Runtime (真实 LLM, 非 mock)
    ├─ PM Agent (需求确认)
    ├─ Architect Agent (系统设计) → AgentMessage → Backend
    ├─ Backend Agent (API) → Artifact
    ├─ Frontend Agent (UI)
    └─ QA Agent (测试) → Validation
    ↓
ConflictResolver (依赖延迟/reorder/serial)
    ↓
Team Validation (All Complete → QA Review → pytest → PASS → DELIVERED)
    ↓
team_execution_state.json (pause/resume/progress)
```

## 2. 数据资产

| 资产 | 内容 | 位置 |
|---|---|---|
| team_execution_state.json | team/tasks/agent/status (pause/resume) | projects/<slug>/ |
| handoff_messages.json | Architect→Backend 交接 (requirement/decision/constraints) | projects/<slug>/ |
| conflict_resolution.json | 冲突处理记录 (strategy: delay/reorder/serial) | projects/<slug>/ |
| team_report.md | 团队生产报告 | projects/<slug>/ |

## 3. 模块计划

```
factory-console/session/
  conflicts.py     (修改: +ConflictResolver — dependency delay/task reorder/serial)
  orchestrator.py  (修改: team mode 真实执行 + Workspace 注入 + Handoff + TeamState)
  teams.py/workspace.py/messages.py (复用/小扩展)
tests/console/test_session_team_execution.py (新增, >=120 测试)
docs/sprint10/S10-057-team-production-validation.md
```

## 4. Real Team Execution Flow

```
execute_project(project_id, mode="team")
  1. 读 team.json + execution_plan.json
  2. required_role → 团队成员分配 (AgentMatcher)
  3. 拓扑排序 (TaskDependencyGraph)
  4. 每任务:
     a. WorkspaceContext 注入 (completed_tasks/artifacts/messages → 上下文)
     b. ConflictResolver 检查 (同文件冲突 → serial/reorder)
     c. 真实 execute_task → AgentRuntime → LLM → artifact
     d. AgentMessage handoff (architect→backend: requirement/decision)
     e. WorkspaceContext 更新
  5. Team Validation: All Complete → QA Review → pytest → PASS → DELIVERED
  6. team_execution_state.json 持久化 (pause/resume/progress)
```

## 5. Agent Collaboration Example

```
Architect 完成系统设计 → AgentMessage {from: architect-agent, to: backend-1,
  type: instruction, content: "Implement REST API per architecture.md,
  constraints: ..."} → handoff_messages.json

Backend 收到上下文: Project=ScorePocket, Completed=[系统设计],
  Artifact=[architecture.md], Message=Architect recommends REST API
```

## 6. Quality Gate (Team Validation)

```
All Agent Tasks Complete → QA Agent Review → pytest → PASS → DELIVERED
(保持 Repair Loop: 失败 → repair → 重验证)
```

## 7. 边界

- 单 Agent mode (solo) 完全兼容
- Team mode 是增强模式
- 所有执行资产化 + 可追踪 + 可恢复
- Core 零改动

---

> 设计完毕 | Real Team Execution + Handoff + ConflictResolver + TeamState + Pilot
