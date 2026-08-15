# S10-056 — Agent Team Collaboration 设计 (完整版)

> 日期:2026-08-15 | Sprint: S10-056 | 9 大模块设计
> 目标: 从"单 Agent 自动开发"升级为"多 Agent 软件生产团队系统"

---

## 1. 架构(扩展层, 不重构主链路)

```
已有主链路 (保持稳定):
  Intent → Product → Engineering → Tasks → AgentMatcher → Execution → Validation → Repair → Delivery
    ↓
新增 Team 扩展层:
  AgentTeam (team.json)                    — 团队抽象 (members/roles)
  Agent Role System (agents.json 扩展)      — role/skills/capabilities
  Task → Team Assignment (required_role)   — AgentMatcher 选择最佳成员
  TaskDependency (task_dependencies.json)   — DAG 数据结构 (顺序执行兼容)
  WorkspaceContext (workspace_context.json) — 共享项目上下文
  AgentMessage (agent_messages.json)        — 基础消息模型
  ConflictDetector (conflicts.json)         — 文件冲突检测 (不自动解决)
  TeamExecutionMode (mode="team")           — 编排器团队模式
```

## 2. 数据模型

### 2.1 AgentTeam (teams.py)
```json
{
  "team_id": "software-team",
  "name": "AI Software Team",
  "members": [
    {"agent": "pm-agent", "role": "product_manager"},
    {"agent": "architect-agent", "role": "architect"},
    {"agent": "backend-1", "role": "backend"},
    {"agent": "flutter-dev", "role": "frontend"},
    {"agent": "qa-agent", "role": "qa"}
  ],
  "projects": [],
  "created_at": "..."
}
```

### 2.2 Agent Role System (agents.py 扩展)
```
支持角色: product_manager/architect/backend/frontend/qa/reviewer/devops
Agent 字段扩展: role/skills/capabilities
不破坏已有 agent (缺省推导: role → capabilities)
```

### 2.3 Task → Team Assignment
```json
{"task_id": "T001", "type": "frontend", "required_role": "frontend"}
```
AgentMatcher: required_role → 候选 agent (team 成员) → skill 匹配 → best

### 2.4 TaskDependency (task_dependencies.json)
```json
{"frontend": ["backend_api"], "ranking": ["match"]}
```
保留顺序执行兼容 (dependencies 为空 → 顺序); DAG 数据结构; 暂不实现复杂调度

### 2.5 WorkspaceContext (workspace_context.json)
```json
{
  "project": "scorepocket",
  "files": ["main.py", "api.py"],
  "completed_tasks": ["T001"],
  "artifacts": ["EXS-xxx.patch"],
  "agent_history": [{"agent": "backend-1", "task": "T001", "result": "success"}]
}
```
让 Agent 知道: 之前谁做过什么

### 2.6 AgentMessage (agent_messages.json)
```json
{"from": "architect-agent", "to": "backend-1", "type": "instruction",
 "content": "Implement REST API according to architecture", "timestamp": "..."}
```
只实现基础消息模型 (append/query)

### 2.7 ConflictRecord (conflicts.json)
```json
{"task_a": "T001", "task_b": "T002", "file": "main.py", "detected_at": "...", "status": "open"}
```
FileOwnership: task → files 记录; ConflictDetector: 检测同文件多任务修改 (不自动解决)

## 3. TeamExecutionMode (orchestrator 扩展)

```python
execute_project(project_id, mode="team")
  Task
  ↓ Dependency Resolver (顺序/DAG 兼容)
  ↓ Agent Matcher (required_role → team member)
  ↓ Agent Execution (真实)
  ↓ Validation
```

## 4. 数据资产 (全部落盘)

```
~/.factory/teams/team.json              — 团队
~/.factory/teams/task_dependencies.json — 依赖图
~/.factory/projects/<slug>/workspace_context.json — 共享上下文
~/.factory/teams/agent_messages.json    — 消息
~/.factory/teams/conflicts.json         — 冲突记录
```

## 5. 模块计划

```
factory-console/session/
  teams.py       (新增: AgentTeam/TeamRegistry/TeamService)
  roles.py       (新增: RoleSystem — 角色→capabilities 推导) 或并入 agents.py
  dependencies.py (新增: TaskDependencyGraph)
  workspace.py    (新增: WorkspaceContext)
  messages.py     (新增: AgentMessageStore)
  conflicts.py    (新增: FileOwnership/ConflictDetector)
  agents.py       (修改: +capabilities 推导, 兼容)
  orchestrator.py (修改: +TeamExecutionMode, 兼容)
  actions.py/intent.py/router.py (修改: +team 集成)
tests/console/test_session_team.py (>=100 测试)
docs/sprint10/S10-056-agent-team-collaboration.md
```

## 6. 开发原则

```
1. 不破坏 S10-049~055 (主链路兼容)
2. 优先扩展, 不重构
3. 所有能力资产化 (json)
4. 所有执行可审计
5. 所有失败可恢复
6. 真实执行能力, 不做 mock-only
```

## 7. 边界

- TeamExecutionMode 是 orchestrator 可选模式 (默认单 Agent 兼容)
- DAG 只数据结构, 不实现复杂调度
- Conflict 只检测不解决
- Message 只基础模型
- Core 零改动

---

> 设计完毕 (完整版) | 9 大模块 | Team Execution 扩展层
