# S10-063 — Production Governance, Cost Control & Human Review Gate 架构设计

> 日期:2026-08-15 | Sprint: S10-063 | 架构 (基于 GAP 分析 G1-G11)
> 核心: AUTONOMY ≠ UNCONTROLLED — 让自主生产"知道不能继续"→ STOP → EXPLAIN → WAIT → RESUME

---

## 1. 架构

```
                     ┌──────────────────────┐
                     │    ExecutionPolicy   │  (G6: AUTO/SAFE_AUTO/REVIEW/MANUAL)
                     └──────────┬───────────┘
                                ↓
  ┌─────────────┐   ┌───────────┴───────────┐   ┌────────────────┐
  │ ProjectBudget│→ │    BudgetEnforcer     │→  │  LoopGuard     │
  │ (G1)         │   │ 80%→WARN 90%→REVIEW  │   │ (G7: 组合总闸)  │
  │              │   │ 100%→BLOCK (G2)      │   │                │
  └─────────────┘   └───────────┬───────────┘   └───────┬────────┘
                                ↓                        ↓
  ┌──────────────────────┐   ┌──────────────────────────────┐
  │     CostLedger       │   │         ReviewGate           │
  │ (G3/G4: usage record │   │ (G5: REQUEST_REVIEW →        │
  │  + 聚合 attribution)  │   │  WAITING → APPROVED/REJECTED)│
  └──────────────────────┘   └──────────────┬───────────────┘
                                            ↓
  ┌─────────────────────────────────────────────────────────┐
  │          AuditCorrelation (G8: execution_id 全链)       │
  └─────────────────────────────────────────────────────────┘
                                            ↓
  ┌─────────────────────────────────────────────────────────┐
  │     StatusModel (G9) + Recovery/Resume (G10) + CLI (G11)│
  └─────────────────────────────────────────────────────────┘
```

## 2. ProjectBudget (新增 session/budget.py)

```
@dataclass ProjectBudget:
  max_total_tokens: int = 0 (0=无限)
  max_total_cost: float = 0.0
  max_llm_calls: int = 0
  max_replans: int = 5
  max_retries: int = 1
  max_repairs: int = 2
  max_task_count: int = 0
  max_execution_time: float = 0.0 (秒)
  max_concurrent_agents: int = 1
  warn_ratio: float = 0.8
  review_ratio: float = 0.9

层级: Project → Sprint → Task → Agent Execution → LLM Call
每层产生 usage → 聚合计算 project/sprint/task/agent/planning/execution/repair/replanning cost
```

## 3. BudgetEnforcer (budget.py 内)

```
check(budget, usage) -> {level: "ok"|"warn"|"review"|"block", reason, usage}
  80% → WARNING (继续)
  90% → REVIEW_REQUIRED (停止, 等审批)
  100% → BLOCK (禁止 LLM/retry/repair/replan/new task)
enforce 应用于: LLM planning / task proposal / agent execution / retry / repair / replanning
```

## 4. CostLedger (新增 session/cost_ledger.py)

```
CostRecord: {project_id, sprint_id, task_id, agent_id, role, purpose,
             provider, model, input_tokens, output_tokens, total_tokens,
             estimated_cost, latency, timestamp, parent_execution_id}
purpose: DISCOVERY/PLANNING/TASK_PROPOSAL/PLAN_CRITIC/EXECUTION/REPAIR/REPLANNING/GAP_ANALYSIS/OTHER
聚合: project_total / sprint_total / task_total / agent_total /
      planning/execution/repair/replanning 分项
复用: AgentRuntime usage → record; planning_trace token_usage → record
```

## 5. ReviewGate (新增 session/review_gate.py)

```
REQUEST_REVIEW → WAITING_FOR_REVIEW → APPROVED/REJECTED → CONTINUE/BLOCK
操作: approve(review_id, reviewer) / reject / resume / cancel
ReviewRecord: {reason, trigger, decision, created_at, reviewed_at, reviewer,
               context, affected_tasks, estimated_cost, risk}
触发: 高成本/高风险/反复失败/多次 replan/LLM confidence 低/proposal 不稳定/
      无法解决 conflict/超 budget
真正停止: status=WAITING_FOR_REVIEW 时执行循环必须停 (不偷偷继续)
```

## 6. ExecutionPolicy (新增 session/execution_policy.py)

```
class ExecutionPolicy:
  AUTO: 全部自动 (高 confidence + 低风险)
  SAFE_AUTO: 自动 + review 触发条件
  REVIEW_REQUIRED: 特定操作必须人工
  MANUAL: 全人工
  can_execute(context) -> (allowed, reason)
  can_retry / can_repair / can_replan / can_create_task
统一 policy 层, 不在 orchestrator 散落 if/else
```

## 7. LoopGuard (新增 session/loop_guard.py)

```
防护: Agent retry / Repair / Replanning / Task proposal / LLM planning
限制: max_retry / max_repair / max_replan / max_generated_tasks /
      max_same_failure (同 task 同 failure 反复) / max_same_decision /
      max_total_execution (组合总闸)
发现: 同 task + 同 failure + 同 proposal + 同 decision 反复 → BLOCK/REQUEST_REVIEW
```

## 8. AuditCorrelation (修改 audit.py + trace)

```
统一 execution_id: 用户想法 → Discovery → Product → Plan v1 → 决策 → 执行 →
                   验证失败 → Gap → LLM → Proposal → Plan v2 → ...
所有重要决策带 execution_id + parent_execution_id
planning_trace 增加 task_id/agent_id/parent_execution_id 关联
```

## 9. StatusModel (统一状态)

```
DRAFT/PLANNING/READY/RUNNING/WAITING_FOR_REVIEW/BLOCKED/REPAIRING/REPLANNING/
VALIDATING/READY_FOR_ACCEPTANCE/DELIVERED/FAILED/CANCELLED
统一单一来源 (不引入第二套): orchestrator ExecutionState + TeamExecutionState 对齐
```

## 10. Recovery/Resume

```
WAITING_FOR_REVIEW → approve → resume (跳过 completed, 不重复执行)
进程中断 → reload state → resume (workspace/artifacts/decisions/plan_version/
cost/validation 不丢失)
```

## 11. CLI 命令

```
factory status   — Project/Status/PlanVersion/Completed/Running/Pending/AgentTeam/
                    TokenUsage/EstimatedCost/Budget/Replans/Repairs/Retries/Review
factory budget   — 预算查询
factory history  — 生产历史 (audit chain)
factory review   — 待审列表 + approve/reject
factory resume   — 恢复执行
不破坏现有 CLI 架构 (新增 action, 不重构)
```

## 12. 真实生产验证 (8 场景)

```
CASE A: 正常生产 → DELIVERED
CASE B: 80% → WARNING (继续)
CASE C: 90% → WAITING_FOR_REVIEW → approve → 继续
CASE D: 100% → BLOCKED (禁 LLM)
CASE E: Replanning loop → 最终 BLOCK/REVIEW
CASE F: WAITING → approve → resume → continue → deliver
CASE G: 中断 → reload → resume (不重复 completed)
CASE H: Cost attribution (Total/Planning/Execution/Repair/Replanning/Agent/Task)
```

## 13. 模块计划

```
新增: session/budget.py + cost_ledger.py + review_gate.py +
      execution_policy.py + loop_guard.py
修改: orchestrator.py (接入 enforcer/review/policy/loop guard)
      planning_trace.py (task_id/agent_id 关联)
      audit.py (correlation id)
      actions.py/commands.py (CLI: status/budget/history/review/resume)
测试: test_session_budget.py + test_session_cost_ledger.py +
      test_session_review_gate.py + test_session_execution_policy.py +
      test_session_loop_guard.py + test_session_governance_integration.py (>=150)
```

## 14. 边界

- 不引入第二套状态/cost/decision 系统
- 复用 execution_records + planning_trace 数据
- 不破坏 S10-055~062 (deterministic/llm/hybrid 全兼容)
- 不重建 provider/cost 系统

---

> 架构完毕 | Budget + Cost + Review + Policy + LoopGuard + Audit + Recovery + CLI
