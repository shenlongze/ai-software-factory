# S10-056 — Agent Team Collaboration

> 日期:2026-08-15 | Sprint: S10-056 | 完整版 9 模块
> 目标: 从"单 Agent 自动开发"升级为"多 Agent 软件生产团队系统"

---

## 1. 架构(扩展层, 主链路稳定)

```
已有主链路 (不变): Intent → Product → Engineering → Tasks → Execution → Validation → Delivery
    ↓
Team 扩展层:
  AgentTeam (team.json)                 — 团队抽象 (5 角色: pm/architect/backend/frontend/qa)
  Agent Role System (roles.py)          — 8 角色 capabilities 推导
  Task → Team Assignment                — required_role → AgentMatcher 选成员
  TaskDependencyGraph                   — DAG 数据结构 (拓扑排序, 顺序兼容)
  WorkspaceContext                      — 共享项目上下文 (谁做过什么)
  AgentMessageStore                     — 基础消息模型 (architect→backend 指令)
  ConflictDetector                      — 文件冲突检测 (记录不解决)
  TeamExecutionMode (mode="team")       — 编排器团队模式
```

## 2. 数据模型

| 资产 | 内容 | 落盘 |
|---|---|---|
| team.json | team_id/name/members/roles/projects | ~/.factory/teams/ |
| task_dependencies.json | task → depends_on | ~/.factory/teams/ |
| workspace_context.json | project/files/completed_tasks/artifacts/agent_history | projects/<slug>/ |
| agent_messages.json | from/to/type/content | ~/.factory/teams/ |
| conflicts.json | task_a/task_b/file/status=open | ~/.factory/teams/ |

## 3. 真实验证 (2026-08-15)

```
Team Execution (orchestrator mode="team"):
  任务: T001 需求分析(required_role=product_manager)
        T002 架构设计(required_role=architect)
        T003 实现API(required_role=backend)
  依赖: T003→T002→T001
  执行顺序 (拓扑): T001 → T002 → T003 ✅
  角色分配: T001→pm-agent, T002→architect-agent, T003→backend-1 ✅
  停在 USER_ACCEPTANCE (验收门) ✅

Conflict Detection:
  T001/T002 都改 main.py → conflicts.json
  ConflictRecord {task_a: T001, task_b: T002, file: main.py, status: open} ✅
  (检测不阻塞, 不自动解决)

solo mode 缺省完全不变 (execute_project 兼容) ✅
```

## 4. 模块

| 模块 | 职责 | 状态 |
|---|---|---|
| teams.py | AgentTeam + TeamRegistry (software-team 5 成员) + TeamService | ✅ |
| roles.py | RoleSystem (8 角色 + 规范化匹配: 空格/下划线等价) | ✅ |
| dependencies.py | TaskDependencyGraph (Kahn 拓扑, 顺序兼容) | ✅ |
| workspace.py | WorkspaceContext (共享上下文) | ✅ |
| messages.py | AgentMessageStore (基础消息) | ✅ |
| conflicts.py | FileOwnership + ConflictDetector (记录不解决) | ✅ |
| orchestrator.py | mode="team": 角色匹配 + 拓扑 + 冲突 + Workspace 更新 | ✅ |
| actions.py/intent.py/router.py | 团队执行/依赖/冲突视图 | ✅ |

## 5. 测试

```
新增: test_session_team_models.py 174 + test_session_team.py 144 = 318 测试
全量: 9488 passed, 0 failed (基线 9344 → +144, 零回归)
覆盖: Team/Roles/Dependency/Workspace/Messages/Conflicts/TeamExecution/回归
```

## 6. AI 软件公司团队

```
产品经理 (pm-agent)     → ProductIntent/PRD
架构师 (architect-agent) → 工程规划
开发 (backend-1/flutter-dev) → Agent Runtime 执行
测试 (qa-agent)         → Validation
审计 (ProductionTrace)  → 完整生产审计
团队协作 (S10-056)      → 角色分配 + 依赖 + 冲突 + 共享上下文

= 多 Agent 软件生产团队系统
```

## 7. 未来扩展

```
冲突自动解决:  ConflictResolver (当前记录不解决)
消息闭环:       AgentMessage → 执行反馈 (当前基础模型)
复杂调度:       DAG → 并行执行 (当前拓扑顺序)
技能学习:       Metrics → 角色能力强化
```

## 8. 边界

- 主链路零重构 (solo mode 完全兼容)
- 所有能力资产化 (5 个 json)
- 失败可恢复 (空 plan/空团队兜底)
- Core 零改动

---

> S10-056 文档完毕 | Agent Team Collaboration 落地 | 318 新测试 | 9488 全绿
