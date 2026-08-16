# S10-063 — Production Governance, Cost Control & Human Review Gate

> 日期:2026-08-15 | Sprint: S10-063 | Production Governance
> 状态: 让自主生产"知道不能继续"→ STOP → EXPLAIN WHY → WAIT FOR HUMAN → RESUME

---

## 1. 为什么需要治理

S10-055~062 已能"自主生产",但无成本边界/人工审批/审计。核心原则: **AUTONOMY ≠ UNCONTROLLED**。

## 2. 新能力

| 能力 | 说明 |
|---|---|
| ProjectBudget | 统一预算 (max_total_tokens/cost/llm_calls/replans/retries/repairs/task_count/time/concurrent) |
| BudgetEnforcer | 80% WARN (继续) / 90% REVIEW (停止) / 100% BLOCK (禁止 LLM/retry/repair/replan/new_task) |
| CostLedger | CostRecord (project/task/agent/role/purpose/provider/model/tokens/cost/latency) + 聚合 |
| ReviewGate | REQUEST_REVIEW → WAITING → approve/reject/cancel; 真正阻止执行 |
| ExecutionPolicy | AUTO / SAFE_AUTO / REVIEW_REQUIRED / MANUAL + risk 判定 |
| LoopGuard | same_failure / same_decision / total_execution 组合总闸 |
| planning_trace 关联 | task_id/agent_id/project_id/parent_execution_id |
| CLI | factory status / budget / review (approve/reject) |

## 3. 真实生产验证 (2026-08-15)

```
CASE C (budget 90%): status=waiting_for_review
  reason="预算消耗比 90.00% 已达评审线 90% — 停止执行等待审批"
  → ReviewGate 创建 open review → approve → approved ✅

CASE F (resume): approve 后 + 预算充足 → T001/T002/T003 全执行 → user_acceptance ✅

CASE D (budget 100%): status=blocked
  reason="BUDGET BLOCK: action=execute 被禁止 — 总预算已耗尽"
  → 任务被阻止执行 (calls=[]) ✅ 不烧 token

CASE H (Cost Attribution): total_cost=0.01 USD / total_tokens=10000 /
  by_purpose={EXECUTION: 0.01} ✅
```

## 4. 测试

```
批次 A (模型层): budget(54) + cost_ledger(39) + review_gate(33) + execution_policy(36) + loop_guard(27) = 189
批次 B (集成层): governance_integration(33) + governance_cli(34) = 67
合计: 256 新测试 (>=150 目标达成)
全量: 10678 passed + 1 skipped, 0 failed (10422 基线 → +256, 零回归)
```

## 5. 回答核心验收

"AI Factory 是否已经具备安全自主生产的基本生产治理能力?"

✅ **是**:
- 成本过高 → 知道不能继续 (BLOCK/REVIEW)
- 风险过高 → REQUEST_REVIEW → WAITING_FOR_REVIEW (真正停止)
- 重复失败 → LoopGuard 组合总闸
- 无限重规划 → max_replan + 超限 REQUEST_REVIEW
- LLM 不确定 → confidence 阈值 → REVIEW
- 需要人工决策 → STOP → EXPLAIN WHY (reason 落盘) → WAIT → RESUME

## 6. 技术债

- 无人工审批 UI (CLI approve/reject 已备)
- CostLedger 未自动关联 planning_trace (接口已备)
- ExecutionPolicy 未接入所有路径 (orchestrator 核心路径已接入)
- 无 max_execution_time 计时器 (预算字段已备)

## 7. 下一 Sprint 建议

```
S10-064 — 发布行动 (终极叙事 + 治理就绪)
  "用户一句话 → AI 团队自主生产 (理解/规划/执行/观察/重规划/交付)
   + 安全边界 (成本/风险/审批/审计/恢复)"
- 或 S10-064: Review UI + Cost Ledger 自动关联 + 完整 Audit Trail
```

---

> S10-063 文档完毕 | Production Governance | 256 新测试 | 10678 全绿
