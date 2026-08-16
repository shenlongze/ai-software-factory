# S10-065 — GAP ANALYSIS

> 日期:2026-08-16 | Sprint: S10-065 | P0 现状审查
> 战略: 从 BUILD THE FACTORY → USE THE FACTORY
> 目标: 用户自然对话使用 AI Software Factory

---

## 16 问回答

### 1. conversation.py 怎么工作?
```
ConversationManager (session/conversation.py):
  ConversationState: DISCOVERY → CLARIFICATION → PRODUCT_CONFIRMATION →
    CONFIRMATION → PROJECT_CREATION → EXECUTION → DONE
  start_product_discovery(text) → 初始化 ProductIntent + 追问 problem → user → core_features
  _next_product_question() → 缺什么问什么 (不静默)
  _set_product_field / _enter_product_confirmation
✅ 已有基础产品发现流程 (S10-050), 但只追问 3 字段, 无使用场景/非功能/MVP
```

### 2. intent.py 怎么工作?
```
IntentParser: 关键词规则 (_KEYWORD_RULES) + INTENT_* 常量
  创建产品: ("做一个","开发一个" + 产品标记) → create_product
  准备: ("准备开发","生成工程计划") → prepare_project
  执行: ("开始开发","开始执行") → execute_project
  验收: ("通过验收","验收通过") → accept_project
✅ 已有自然语言路由 (中文关键词), 但用户需知道分步命令
```

### 3. ProductIntent 字段?
```
name/problem(必填)/user(必填)/platform/core_features(必填)/status/raw/session_id
( product.py )
✅ 结构完整, 必填校验 (missing_fields)
```

### 4. router 如何识别用户意图?
```
Router.route(intent, registry) → DEFAULT_ROUTES 映射 intent_type → action name
✅ 意图→action 映射
```

### 5. 当前 actions 有哪些?
```
21 个: create_project/create_product/generate_prd/prepare_project/execute_project/
  project_progress/accept_project/workforce/team(5)/factory_status/budget/review/...
✅ 全链路 action
```

### 6/7/8. create/prepare/execute 如何调用?
```
create_product(context): _product_from_context → missing_fields 校验 → 创建
prepare_project(context): 确认门 → Product→PRD→engineering→tasks→execution_plan
execute_project(context): 确认门 → orchestrator.execute_project → 执行
✅ 可调用, 但均为独立步骤 (用户需逐步触发)
```

### 9. lifecycle 在哪些地方定义?
```
pipeline.py Lifecycle: IDEA→PRODUCT_DEFINED→ENGINEERING_READY→EXECUTION_READY→
  DEVELOPMENT→TESTING→VALIDATION_PASS→USER_ACCEPTANCE→DELIVERED
orchestrator ExecutionState: status (running/failed/delivered/review_required)
S10-063 governance_status (waiting_for_review/blocked)
⚠️ 三处分散 — 无统一用户视角
```

### 10/11. execution_state / TeamExecutionState?
```
ExecutionState (orchestrator.py): 任务状态/生命周期/plan_version/replan_count/governance
TeamExecutionState (team_state.py): 团队任务级状态 (team_execution_state.json)
✅ 都有
```

### 12. Governance state 如何获取?
```
ExecutionState.governance_status / governance_reason / governance_warnings
ReviewGate.status(project_id) → none/waiting/approved/rejected
✅ 有
```

### 13. ReviewGate 如何恢复执行?
```
ReviewGate.approve(review_id, reviewer) → status=approved
orchestrator.resume() → 从 execution_state 继续 pending/failed (跳过 completed)
✅ 有机制, 但无用户友好 view/选项
```

### 14/15. CostLedger / PlanningTrace 获取?
```
CostLedger.records(project_id)/aggregate(project_id) → total/by_purpose/by_agent/by_task
PlanningTrace.load()/record() → planning_trace.json
✅ 有, 但无自动关联 (task_id/agent_id 可关联)
```

### 16. 如何不破坏旧 CLI 增加自然语言流程?
```
✅ 增量: 新增 action + intent 规则 (旧关键词/命令不动)
  guided_start ("我想做X") → DiscoverySession → 确认 → 内部调 create/prepare/execute
```

---

## CURRENT → TARGET → GAP → IMPACT → IMPLEMENTATION

| # | CURRENT | TARGET | GAP | IMPACT | IMPLEMENTATION |
|---|---|---|---|---|---|
| G1 | ConversationManager 追问 3 字段 (problem/user/core_features) | 完整 DiscoverySession (多字段澄清 + 信息足够判断 + summary + confirm) | 无独立可持久化 DiscoverySession; 缺使用场景/非功能/MVP 追问; 无需求摘要 | 用户无法自然对话完成产品定义 | session/discovery.py: DiscoverySession (state/fields/questions/summary/confirm) |
| G2 | execute 后仅 project_progress (任务数) | ProductionSession 统一视图 (phase/agent/task/budget/cost/replan/review) | 无统一生产过程视图 | 用户看不到"AI 团队工作中" | session/production_session.py: 聚合 ExecutionState/TeamState/CostLedger/ReviewGate |
| G3 | ReviewGate 有但无 UX | Review View (reason/current/budget/options APPROVE/REJECT/CANCEL) | 无用户友好审批界面 | 用户不知道怎么处理 WAITING_FOR_REVIEW | actions.py: review_view + approve/reject/cancel 引导 |
| G4 | 状态分散 (Lifecycle/ExecutionState/governance) | 统一用户生命周期 (IDEA→DISCOVERY→...→DELIVERED) | 无用户视角状态机 | 用户无法理解"现在到哪了" | session/user_lifecycle.py: 映射层 (不破坏内部) |
| G5 | 需知道命令关键词 | "继续"/"开始生产"/"为什么停了" 自然语言 | 引导式 CLI 缺失 | 非技术用户无法使用 | intent.py 新规则 + actions.py guided actions |
| G6 | CostLedger/PlanningTrace 独立 | 自动关联 (project/task/agent/trace_id) | 无关联 | 无法回答"为什么花这些钱" | cost_ledger.py: record 时自动 attach trace |
| G7 | max_execution_time 字段有但未接 | 真正生效 (超时→停止) | 未实现计时器 | 长跑任务无时间边界 | orchestrator.py: _run_queue 计时检查 |

---

## 关键结论

**不是从零做 Discovery** — conversation.py 已有基础产品发现(S10-050)。GAP 是:
1. 独立可持久化的 DiscoverySession(状态可恢复)
2. 更完整的澄清字段(使用场景/非功能/MVP)
3. 需求摘要 + 确认流程
4. ProductionSession 统一视图
5. Human Review UX
6. 引导式自然语言入口

## 复用 (不重写)

```
ProductIntent / create_product / prepare_project / execute_project /
ConversationManager / Router / ExecutionState / TeamExecutionState /
CostLedger / ReviewGate / PlanningTrace / Governance (S10-063) 全部
```

## 不该现在做 🚫

```
重写 Orchestrator/AgentRuntime/Team/Replanning/Governance/ProductIntent
新 Agent Framework / 新 LLM abstraction / UI 重构底层
Marketplace/多租户/云部署/SaaS/Billing/OAuth/大规模并行
```

---

> GAP 完毕 | G1-G7 | 复用充分 | 核心: Discovery + ProductionSession + Review UX
