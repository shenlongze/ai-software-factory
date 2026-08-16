# S10-064 — GAP REPORT (完整版)

> 日期:2026-08-15 | Sprint: S10-064 | P0 现状审查
> 战略: 从 BUILD THE FACTORY → USE THE FACTORY
> 目标: 让完全不了解内部架构的用户, 从"我想做一个软件"开始使用 AI Factory

---

## 1. 当前用户入口

```
CLI: ai-factory (cli_factory.main) → session 会话 (session.py)
  欢迎横幅: "AI Factory v0.2 / AI Workforce Operating System"
  用户输入 → intent 路由 → action → ActionResult

现有 action (21 个): create_project/create_product/generate_prd/prepare_project/
  execute_project/project_progress/accept_project/workforce/team/...
用户可自然语言: "我想开发一个台球计分APP" → INTENT_CREATE_PROJECT → create_product
```

**回答**:
- 用户从 CLI 会话进入 ✅
- 产品创建可用自然语言 ✅
- 但后续步骤需知道命令关键词: "准备开发"/"开始开发"/"通过验收" (半技术型)

## 2. 当前 Discovery 能力

```
ProductIntent (product.py):
  name/problem(必填)/user(必填)/platform/core_features(必填)/status/raw/session_id
  missing_fields() → 缺失字段列表 → create_product 报"缺失必填字段"错误

现状: 用户一句话 → 若字段齐全 → 立即创建; 若缺失 → 报错 (非澄清)
```

**缺失**: 无 DiscoverySession — AI 不主动澄清/追问/确认, 不判断"信息是否足够"

## 3. 当前 Product/Project 生命周期

```
Lifecycle (pipeline.py): IDEA → PRODUCT_DEFINED → ENGINEERING_READY →
  EXECUTION_READY → DEVELOPMENT → TESTING → VALIDATION_PASS →
  USER_ACCEPTANCE → DELIVERED
ExecutionState: status (running/failed/delivered/review_required/blocked)
S10-063 新增: governance_status (waiting_for_review/blocked)
```

**缺失**: 状态分散 (Lifecycle/ExecutionState/governance_status), 无统一用户视角状态机 (NEW→DISCOVERY→PRODUCT_READY→...→DELIVERED)

## 4. 当前 Production Session

```
无 ProductionSession — 用户执行 execute_project 后只能查询 project_progress
(任务完成数 + 生命周期), 无:
  - 实时进度 (当前 Agent/任务/Plan version)
  - Team 成员状态视图 (PM✓/Architect✓/Backend●/...)
  - Budget/Cost 实时显示
  - Replans/Retries 计数
```

## 5. 当前 Governance UX

```
S10-063 已实现: ReviewGate (request/approve/reject/cancel) + factory_review action
  + WAITING_FOR_REVIEW/BLOCKED 状态 + resume
但: 无用户友好 review 视图 (Reason/Current/Options 展示)
    approve/reject 需调用 factory_review action (非引导式)
```

## 6. 当前 CLI/Console 能力

```
✅ 会话式输入 (自然语言 → intent → action)
✅ 命令关键词路由 (中文)
✅ factory_status/factory_budget/factory_review (S10-063)
❌ 无引导式界面 (Welcome → What do you want to build? → ...)
❌ 无实时生产进度流
❌ 无 Review 决策界面 (Approve/Reject/Cancel 选项)
```

## 7. 缺失能力汇总

| # | 缺失 | 严重度 |
|---|---|---|
| G1 | DiscoverySession (澄清对话/信息足够判断/确认) | P0 |
| G2 | ProductionSession 视图 (实时进度/Team/Task/Plan/Budget) | P0 |
| G3 | Human Review UX (Reason/Options/Approve/Reject/Cancel) | P0 |
| G4 | 统一用户生命周期状态机 | P1 |
| G5 | 引导式 CLI 流程 (What do you want to build?) | P1 |
| G6 | CostLedger ↔ PlanningTrace 自动关联 | P1 |
| G7 | max_execution_time 计时器生效 | P1 |
| G8 | 交付摘要 (产物/路径/成本/下一步) | P2 |

## 8. P0 / P1 / P2 排序

```
P0 (本 Sprint 必做):
  - Interactive Discovery (DiscoverySession: 澄清→ProductIntent→确认→创建)
  - Production Session 视图 (实时状态展示)
  - Human Review UX (Approval 界面)

P1 (本 Sprint 做):
  - 统一生命周期状态机 (用户视角)
  - 引导式 CLI (欢迎 → 我想做什么 → 澄清 → 确认 → 生产)
  - CostLedger ↔ PlanningTrace 关联
  - max_execution_time 生效

P2 (本 Sprint 可选/不做):
  - 交付摘要 (增强)
```

## 9. 建议架构

```
新增:
  session/discovery.py      — DiscoverySession (澄清对话/信息提取/确认)
  session/production_session.py — ProductionSession 视图 (聚合 orchestrator 状态)
  session/user_lifecycle.py — 统一用户生命周期状态机
修改:
  session/actions.py        — guided_start (引导式入口) + review_approve/reject/cancel UI
  session/conversation.py   — 引导增强
  session/intent.py         — 新意图路由 (我想做一个X → discovery)
  session/cost_ledger.py    — planning_trace 自动关联
  session/orchestrator.py   — max_execution_time 生效

复用: ProductIntent/create_product/prepare_project/execute_project/
  TeamExecutionMode/Governance (S10-063) 全部现有引擎 — 只包装不重写

用户视角:
  我想做一个软件 → AI 澄清 (DiscoverySession) → 产品定义 → 确认
  → ProductionSession 实时进度 → 遇问题 AI 自主/请求用户 (Review UX)
  → 完成 → 交付
```

## 10. S10-064 最终实施范围

```
P0: DiscoverySession + ProductionSession 视图 + Human Review UX
P1: 用户生命周期状态机 + 引导式 CLI + Cost/Trace 关联 + execution_time
P2: 交付摘要 (若时间允许)
禁止: Marketplace/多租户/云部署/SaaS/Billing/OAuth/新 Agent 决策类型

测试: >=120 (discovery>=30 + production session>=30 + review UX>=20 + cost/trace>=10 + 生命周期>=30)
真实 E2E: 用户一句话 → 澄清 → 确认 → 真实 Agent 生产 → 治理 → DELIVERED (ScorePocket)
```

---

> GAP REPORT 完毕 | P0: Discovery + Production Session + Review UX | 复用现有引擎
