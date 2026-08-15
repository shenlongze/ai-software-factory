# S10-059 — GAP ANALYSIS

> 日期:2026-08-15 | Sprint: S10-059 | P0 现状审查
> 审查方式: 读取真实代码 (orchestrator/teams/roles/dependencies/workspace/messages/conflicts/team_state/quality/agents)

---

## 已经具备 ✅

| 能力 | 位置 | 说明 |
|---|---|---|
| TeamExecutionMode | orchestrator.py `execute_project(mode="team")` | required_role → AgentMatcher + 拓扑 + TeamRunContext |
| AgentMatcher | agents.py | skill × 成功率 × 成本 → {agent, score, reason} |
| TaskDependencyGraph | dependencies.py | Kahn 拓扑排序 (顺序兼容) |
| WorkspaceContext | workspace.py | project/files/completed_tasks/artifacts/agent_history |
| AgentMessageStore | messages.py | 基础消息 (append/query) |
| Handoff | messages.py HandoffStore + orchestrator | architect→backend 交接 → handoff_messages.json |
| DecisionStore | messages.py | ArchitectDecision → decision_objects.json (S10-058) |
| ConflictDetector | conflicts.py FileOwnership + detect | 同文件多任务 → ConflictRecord (open) |
| ConflictResolver | conflicts.py resolve | dependency_delay/task_reorder/serial_execution → 重排 |
| TeamExecutionState | team_state.py | pause/resume/progress |
| Validator/Repair | quality.py | validate/validate_command/validate_frontend + RepairManager |
| ExecutionOrchestrator | orchestrator.py | solo/team 双模式 + Workspace 注入 + team_report |

## 缺失 ❌ (S10-059 目标)

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **HandoffDecisionEngine** | 无独立决策引擎; 执行顺序是固定拓扑, 不是决策驱动 |
| G2 | **Workspace Reservation** | 无 active_agent/active_task/reserved_files/workspace_snapshot/changed_files; 无"写权限"概念 |
| G3 | **Conflict → Execution Decision** | ConflictResolver 只输出重排, 不返回 CONTINUE/BLOCK/SERIALIZE 决策 |
| G4 | **Decision 驱动执行** | before_task 只 detect 记录, 不阻塞/不改变执行策略 |
| G5 | **决策可解释性资产化** | 无 handoff_decisions.json / workspace_locks.json |

## 半成品 ⚠️

| # | 半成品 | 现状 → 需要 |
|---|---|---|
| H1 | ConflictResolver | 有 resolve 重排 → 需升级: detect → classify → resolve → execution decision (决策对象返回) |
| H2 | WorkspaceContext | 有 files/artifacts → 需加 reservation 机制 (acquire/release) |
| H3 | TeamRunContext.before_task | 只记录冲突 → 需调 DecisionEngine → SERIALIZE/BLOCK 决策 |
| H4 | Handoff | 记录交接 → 需决策引擎消费 (判断下一 Agent 所需上下文) |

## 需要重构 🛠

| # | 重构 | 原因 |
|---|---|---|
| R1 | ConflictResolver.resolve 返回结构 | 需增加 decision 对象 (含 reason/strategy/conflicting_tasks), 供 orchestrator 消费 |

## 不应该现在做 🚫 (S10-059 边界)

- 复杂 Git merge / DAG 并行执行 / Reviewer Agent 大系统
- PyPI 发布 / GitHub marketing / UI 大改 / SaaS / 账号 / Billing / 云部署 / 多租户
- 无关基础设施重构

---

## S10-059 设计方向

```
P1 HandoffDecisionEngine (新): 
  输入: completed task / artifact / handoff / workspace_context / next task / dependencies / conflicts / agent role
  输出: CONTINUE | BLOCK | RETRY | REPAIR | SERIALIZE | SKIP | REQUEST_REVIEW + reason
  落盘: handoff_decisions.json

P2 Workspace Isolation (扩展 workspace.py):
  acquire_reservation(agent, task, files) → workspace_locks.json
  release_reservation(agent, task)
  核心: 同一文件不能被两个 Agent 同时拥有写权限

P3 ConflictResolver 参与执行 (升级 conflicts.py):
  detect → classify → resolve → execution decision (决策对象含 reason)
  NO_CONFLICT | SERIALIZE | RETRY_WITH_CONTEXT | REQUEST_REVIEW

P4 orchestrator 集成:
  before_task: detect → DecisionEngine → 决策 (SERIALIZE 阻塞等前序释放)
  inject_context: 含 reservations/changed_files
  after_task: release + workspace 更新

P5 真实冲突场景 + P6 可解释性 + P7 测试 >=100 + P8 真实生产验证
```

> GAP 分析完毕 | G1-G5 缺失 | H1-H4 半成品 | R1 重构 | 边界明确
