# S10-049 — Agent Execution Kernel 设计

> 日期:2026-08-15 | Sprint: S10-049 | Phase 0 分析 + Phase 1 架构设计

---

## 1. Phase 0 — 内部分析

### 已完成能力(S10-048)
```
session/action.py       Action + ActionRegistry + ExecutionContext + ActionResult
session/router.py       IntentRouter (声明式 type→action 映射)
session/actions.py      create_project / list_projects / show_status (3 Action)
session/conversation.py ConversationState + ConversationManager
session/confirm.py      ConfirmationGate (敏感 action 确认)
session/session.py      双入口: slash + intent→route→confirm→action
```

### 关键发现
| # | 发现 | 意义 |
|---|---|---|
| F1 | **INTENT_RUN_TASK 已存在** (intent.py:27, "加/修复/写"→objective) | 意图解析已支持 |
| F2 | **router 无 run_task→action 映射** | 缺路由 |
| F3 | **registry 无 run_task/execute_task action** | 缺能力 |
| F4 | **cmd_exec_run(root, args) 可直接薄调** (project/task/objective/agent/employee/provider/test_cmd/json) | 真实执行链可用 |
| F5 | **AgentRuntime 存在** (agent_runtime.py:113), exec CLI 已封装 | 不重复造轮子 |
| F6 | tasks 有真实数据 (E2-001/EX-001) | 可真实执行 |

### 当前缺口
```
G1: 无 agent.execute_task action (Intent → Agent 执行)
G2: router 未映射 run_task
G3: Conversation 未接澄清 (缺 project/task 时)
G4: 无 AgentExecutionResult 统一结构
G5: 无执行审计记录 (intent/action/agent/result)
```

### S10-049 最小实现范围
```
P0: agent.execute_task Action (薄调 exec.cli.cmd_exec_run — 真实 Agent Runtime)
P1: router 映射 run_task → execute_task
P2: AgentExecutionContext (在现有 ExecutionContext 上加 task_id/agent_id/project_id)
P3: Agent Selector 最小版 (task 特征 → agent; 默认 backend-1)
P4: Conversation 澄清 (缺 project/task → CLARIFICATION)
P5: 执行审计记录 (execution record 写入)
```

---

## 2. Phase 1 — 架构设计

### 2.1 Agent Execution Kernel 架构

```
Intent ("帮我实现登录功能")
    ↓
IntentParser → IntentObject {type: run_task, params: {objective: "实现登录功能"}}
    ↓
IntentRouter (run_task → agent.execute_task)
    ↓
ActionRegistry.get("agent.execute_task")
    ↓
ConfirmationGate (run_task 敏感 → 确认)
    ↓
AgentExecutionContext
    {session_id, project_id, task_id, agent_id, workspace, intent, metadata}
    ↓
Agent Selector (最小: task 特征 → agent; 默认 backend-1)
    ↓
Action.execute → 薄调 exec.cli.cmd_exec_run(root, args)
    ↓
AgentRuntime (真实 LLM → 沙箱 → patch → 产物)
    ↓
AgentExecutionResult {success, agent, artifact, cost, duration}
    ↓
Execution Record (审计: intent/action/agent/task/result/timestamp)
    ↓
Renderer 展示
```

### 2.2 AgentExecutionContext(扩展现有 ExecutionContext)

```python
@dataclass
class AgentExecutionContext(ExecutionContext):
    task_id: str | None = None
    agent_id: str | None = None
    project_id: str | None = None
    # 继承: workspace/session/user/project/intent/metadata (S10-048)
    # 未来: permission/audit/cost_tracking
```

### 2.3 Agent Execution Action(与现有 Action 注册制一致)

```python
Action(
    name="agent.execute_task",
    description="执行开发任务 → Agent Runtime (真实 LLM + 产物)",
    handler=execute_task,
    permission="project",     # 敏感: 需确认
    metadata={"sensitive": True, "category": "execution"},
)
```

### 2.4 Agent Selector(最小版)

```python
def select_agent(intent: IntentObject, context) -> str:
    """最小选择: params.agent_id 优先; 否则按 objective 关键词:
    frontend/flutter/ui → flutter-dev; 其余 → backend-1"""
    agent = intent.parameters.get("agent_id")
    if agent:
        return agent
    objective = str(intent.parameters.get("objective", "")).lower()
    if any(k in objective for k in ("前端", "flutter", "ui", "界面")):
        return "flutter-dev"
    return "backend-1"
```

### 2.5 AgentExecutionResult(统一结构, 不破坏旧接口)

```python
@dataclass
class AgentExecutionResult:
    success: bool
    agent: str
    artifact: str          # patch 路径
    cost: str              # usage 摘要
    duration: str
    result_id: str | None
    error: str | None = None
```

### 2.6 执行审计记录(最小)

```python
def record_execution(record: dict) -> None:
    """写入 ~/.factory/exec/execution_records.json (append) — 未来 audit/cost/replay"""
    # record: {intent, action, agent, task, result, timestamp, result_id}
```

### 2.7 架构符合性

| 原则 | 符合 |
|---|---|
| 不重构已有架构 | ✅ 扩展现有 Action/Registry/Context |
| 不制造假 Agent | ✅ 薄调 cmd_exec_run → 真实 AgentRuntime + LLM |
| 长期方向 (非 Chatbot) | ✅ 管理任务执行 → 产物 + 审计 |
| 注册式可扩展 | ✅ Action/Route/Selector 全声明式 |

---

## 3. 文件计划

```
factory-console/session/
  actions.py        (修改: +execute_task + select_agent + AgentExecutionResult)
  action.py         (修改: +AgentExecutionContext, 或 actions.py 内定义)
  router.py         (修改: 默认映射 + run_task)
  intent.py         (修改: run_task 参数补 task_id/agent_id — 最小)
  conversation.py   (修改: 缺 project/task → CLARIFICATION — 最小)
  audit.py          (新增: record_execution)
  session.py        (修改: 集成 AgentExecutionResult 展示 — 最小)
tests/console/
  test_session_agent_execution.py  (新增, >=30 测试)
docs/sprint10/S10-049-agent-execution-kernel.md (Phase 7)
```

> Phase 1 设计完毕 | P0-P5 最小范围 | 薄调 exec CLI | 审计 + 澄清 + Selector 最小版
