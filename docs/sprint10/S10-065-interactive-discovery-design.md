# S10-065 — Interactive Discovery & Production Session 架构设计

> 日期:2026-08-16 | Sprint: S10-065 | 架构 (基于 GAP 分析 G1-G7)
> 原则: 包装现有能力, 不重写生产引擎 — USE THE FACTORY

---

## 1. 架构

```
用户输入
   ↓
Conversation (现有)
   ↓
Router (现有 + 新意图)
   ↓
┌──────────────────────────────────────────────┐
│ P0-1 DiscoverySession (discovery.py 新增)     │
│   idea → clarify → summary → confirm → done  │
│   包装 ProductIntent (不重写)                  │
└─────────────────────┬────────────────────────┘
                      ↓ (确认后)
┌──────────────────────────────────────────────┐
│ create_product → prepare_project (现有)       │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ P0-2 ProductionSession (production_session.py)│
│   聚合: ExecutionState + TeamState +          │
│   CostLedger + ReviewGate → 统一视图          │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ P0-3 Human Review UX (actions.py)            │
│   ReviewView: reason/current/options          │
│   approve/reject/cancel → resume (现有)      │
└──────────────────────────────────────────────┘
```

## 2. P0-1 DiscoverySession (session/discovery.py)

```
class DiscoveryState:
  DISCOVERING / CLARIFYING / READY_FOR_CONFIRMATION / CONFIRMED / PRODUCT_CREATED / CANCELLED

@dataclass DiscoveryQuestion:
  field / question / required / hint

@dataclass DiscoverySummary:
  name / problem / user / platform / core_features / usage_scenario / notes

class DiscoverySession:
  session_id / user_input / conversation(list) / product_intent / missing_fields /
  clarification_questions / confidence / status / created_at / updated_at

  方法:
  - start(user_input) -> DiscoveryQuestion[] (第一个追问)
  - answer(user_text) -> 更新 ProductIntent + 下一追问 / 缺字段检测
  - summary() -> DiscoverySummary (需求摘要: 产品名/用户/问题/功能/场景)
  - confirm() -> status=CONFIRMED (用户确认后才创建)
  - create_product(workspace) -> 调现有 create_product 逻辑 (薄调, 不复制)
  - cancel() -> CANCELLED
  - save/load (discovery_sessions.json, 失败安全)

  字段追问顺序: problem → user → core_features → usage_scenario → notes
  信息足够: 必填字段 (problem/user/core_features) 全填 → READY_FOR_CONFIRMATION
  包装 ProductIntent (不重写 ProductIntent API)
```

## 3. P0-2 ProductionSession (session/production_session.py)

```
class ProductionPhase:
  STARTING / PLANNING / EXECUTING / VALIDATING / REPLANNING /
  WAITING_FOR_REVIEW / USER_ACCEPTANCE / DELIVERED / BLOCKED / FAILED

@dataclass ProductionEvent:
  timestamp / phase / message / task_id / agent_id / plan_version

class ProductionSession:
  project_id / product_id / lifecycle_state / current_phase / current_task /
  current_agent / completed_tasks / total_tasks / team / plan_version /
  budget / cost / governance_status / pending_review / last_event / progress / events

  方法:
  - from_project(project_dir, slug) -> ProductionSession (聚合现有状态)
    ExecutionState.status → phase 映射
    TeamExecutionState → team 状态
    CostLedger.aggregate → budget/cost
    ReviewGate.status → pending_review
  - view() -> dict (统一用户视图)
  - progress() -> float (0-1)
  - to_markdown() -> 用户可读生产状态文本
  不重新实现 Orchestrator — 只读取/聚合
```

## 4. P0-3 Human Review UX (actions.py)

```
ReviewView (用户友好审批界面):
  status / reason / risk / trigger / current_task / current_agent /
  current_cost / budget_usage / plan_version / options [APPROVE/REJECT/CANCEL]

action:
  - review_view (查看当前待审: 原因/当前/选项)
  - review_approve (参数 review_id → ReviewGate.approve)
  - review_reject (参数 review_id → ReviewGate.reject)
  - review_cancel (参数 review_id → ReviewGate.cancel)
  复用 ReviewGate (不重写), 只做 UX/View/Action 包装
```

## 5. P1-1 Unified User Lifecycle (session/user_lifecycle.py)

```
class UserLifecycle:
  IDEA / DISCOVERY / PRODUCT_DEFINED / PLANNING / READY / PRODUCTION /
  VALIDATION / REVIEW / ACCEPTANCE / DELIVERED / BLOCKED / FAILED / CANCELLED

  map(internal_state, lifecycle, governance_status) -> UserLifecycle (映射层)
  不破坏内部 Lifecycle (pipeline.py) — 只做用户视角映射
```

## 6. P1-2 Guided CLI (intent.py + actions.py)

```
新意图规则 (旧关键词不动):
  "我想做X"/"帮我做X"/"开始做X" → discovery_start (引导 DiscoverySession)
  "继续"/"继续执行"/"继续开发" → resume/continue
  "为什么停了"/"为什么停止" → review_view / governance 原因
  "查看进度"/"进度如何" → production_session_view
  "接受"/"批准"/"同意" → review_approve
  "拒绝" → review_reject
  "取消" → review_cancel
```

## 7. P1-3 CostLedger ↔ PlanningTrace 关联

```
CostLedger.record 增加: trace_id (可选) — 记录时若带 trace_id 则关联
aggregate 增加: by_trace (trace 级成本)
回答: "这次为什么花了这些钱?" → 按 trace_id 关联 planning 决策
```

## 8. P1-4 max_execution_time 生效

```
execute_project 已接受 max_execution_time (预算字段)
_run_queue 增加: 每任务执行前检查 elapsed >= max_execution_time → 停止 (blocked)
```

## 9. 用户流程 (最终体验)

```
"我想做一个台球计分 APP"
  ↓ DiscoverySession.start → "主要给谁用?"
用户回答 → answer → "核心功能?"
用户回答 → answer → "使用场景?"
用户回答 → answer → READY_FOR_CONFIRMATION
  ↓ summary() → "产品名:ScorePocket / 用户:台球玩家 / 功能:... 是否正确?"
用户确认 → confirm() → PRODUCT_CREATED
  ↓ create_product (现有) + prepare_project (现有)
  ↓ ProductionSession.view() → "PM✓ Architect✓ Backend● Frontend○ QA○ 3/12 Plan v2 $0.21/$1.00"
遇到治理问题 → ReviewView: "预算90% 原因:... [继续][拒绝][取消]"
用户 approve → resume (现有) → 继续
  ↓ USER_ACCEPTANCE → DELIVERED
```

## 10. 测试计划 (>=150)

```
Discovery (>=45): start/answer/summary/confirm/cancel/缺字段/多轮/重复/模糊/非法/持久化
ProductionSession (>=45): 各 phase 映射/progress/budget/cost/plan_version/team/事件
Review UX (>=30): view/approve/reject/cancel/resume/状态转换
Lifecycle + Cost/Trace (>=30): 映射层/关联/execution_time
```

## 11. 边界

- 不重写任何生产引擎 (只包装)
- 不破坏现有 ProductIntent/ConversationManager/Router 行为
- 旧 CLI 命令全保留
- 新增全为增量 (新模块 + 新 action + 新 intent 规则)

---

> 架构完毕 | DiscoverySession + ProductionSession + Review UX + Lifecycle + Guided CLI
