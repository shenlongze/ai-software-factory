# S10-063 — GAP ANALYSIS

> 日期:2026-08-15 | Sprint: S10-063 | P0 现状审查
> 审查方式: 读取真实代码 (orchestrator/reasoning/planning_trace/conflicts/agents/audit/execution)
> 目标: AUTONOMY ≠ UNCONTROLLED — 成本/执行/风险/审批/审计/恢复/解释

---

## 核心问题回答 (20 问)

### 1. 当前 cost/token 记录在哪里?
```
- Agent 执行: factory-exec/exec/agent_runtime.py (usage=output.usage → execution_records.json)
- LLM planning: planning_trace.py (token_usage 归一化 {input/output/total_tokens})
- Agent cost_profile: agents.py (静态 avg_cost + 从 execution_records 计算 avg_cost)
→ 存在但分散, 无统一 Cost/Usage Record 关联 project/task/agent/purpose
```

### 2. 当前 max_replan 是什么?
```
- ReplanningEngine decide max_replan=5 (缺省)
- _replan_on_failure 透传 max_replan
→ 有 replan 上限, 但无总预算层次
```

### 3. 是否存在真正的总预算?
```
❌ 无 ProjectBudget — 只有 ContextBuilder truncate (单次上下文 token 裁剪, 非生产预算)
```

### 4/5/6. 单任务预算 / 单 Agent 预算 / 单 Sprint/Project 预算?
```
❌ 全无 — 只有 max_retry (任务重试) / max_replan (重规划) / max_auto_insert (自动插入)
→ 无单任务 token/cost 上限, 无 Agent 预算, 无 Project/Sprint 总预算
```

### 7. LLM 无限循环是否可能发生?
```
⚠️ 部分防护: max_replan / max_auto_insert_tasks / max_total_generated_tasks / auto_mode
→ LLM planning 调用次数无 budget 限制 (可被 replan 触发多次, 但 replan 有上限)
→ 无 max_llm_calls / max_total_tokens 总闸
```

### 8. Replanning 是否可能无限发生?
```
✅ max_replan=5 存在 (超限 → REQUEST_REVIEW)
→ 有防护
```

### 9. Agent retry + repair + replan 是否可能形成乘法爆炸?
```
⚠️ 三者独立上限 (max_retry=1 / repair 单次 / max_replan=5) 但无组合总闸
→ 一个任务可 retry(2) + repair + 触发 replan → 新任务 → 再 retry...
→ 无 max_total_execution / max_same_failure 总闸
```

### 10. REQUEST_REVIEW 当前是否真的能够阻止执行?
```
✅ PlanCritic preflight → status="review_required" + errors (停止执行)
✅ ReplanningEngine REQUEST_REVIEW → review 信号 → 停止队列
→ 能阻止, 但无 approve/reject/resume 流程 (只有状态)
```

### 11. BLOCK / REQUEST_REVIEW / REVIEW_REQUIRED 是否有明确状态?
```
✅ 有: ExecutionState status="review_required" / "blocked" (S10-060 决策)
→ 状态存在, 但缺 WAITING_FOR_REVIEW/APPROVED/REJECTED 流转
```

### 12/13. 用户是否能够恢复一个暂停的项目? resume?
```
✅ resume 存在: 从 execution_state.json 继续 pending/failed (跳过 completed)
✅ _run_queue 的 BLOCK 决策 → "决策已记录, 不无限等待; resume 后可继续"
→ 有基础 resume, 但 WAITING_FOR_REVIEW → approve → resume 无正式接口
```

### 14. 是否能够知道"为什么系统停下来"?
```
✅ state.last_replan_reason / decision reason / review errors
→ 有, 但分散 (reason 在 decision/replanning 记录)
```

### 15/16/17. 钱花在哪里 / 哪个 Agent / 哪个 Task 花了多少钱?
```
⚠️ execution_records: agent_id/task_id/usage (agent 执行) — 有
⚠️ planning_trace: token_usage (LLM planning) — 有, 但无 task_id/agent_id 关联
❌ 无统一聚合: 无法直接回答 project_total / agent_total / task_total / planning/execution/repair 分项
```

### 18. 哪个 LLM decision 导致了成本?
```
⚠️ planning_trace 有 operation (analyze_gap/propose_task/evaluate_plan) + token_usage
→ 可追溯 LLM 决策成本, 但无 parent_execution_id 关联到具体 task
```

### 19. planning_trace 是否能够和 execution trace 关联?
```
❌ planning_trace 无 parent_execution_id / task_id / correlation 字段
→ 不能跨 trace 关联
```

### 20. 当前 audit trail 是否完整?
```
⚠️ ProductionTrace (audit.py) 存在: Project→Feature→Task→Agent→Artifact→Validation→Cost
⚠️ 各资产独立落盘 (execution_state/decisions/gap_analysis/replanning/planning_trace)
❌ 无统一 correlation id 贯穿 用户想法→Discovery→...→Delivery 全链
```

---

## GAP 汇总

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **ProjectBudget** | 无统一预算 (max_total_tokens/cost/calls/replans/retries/repairs/task_count/time) |
| G2 | **Budget Enforcement** | 无 80% WARNING / 90% REVIEW / 100% BLOCK 执行闸 |
| G3 | **Cost/Usage Record** | 无统一 usage 记录 (project/sprint/task/agent/role/purpose 关联) |
| G4 | **Cost Attribution** | 无法聚合 project/agent/task/planning/execution/repair/replanning 成本 |
| G5 | **Human Review Gate** | REQUEST_REVIEW 无 approve/reject/resume/cancel 正式流程 |
| G6 | **ExecutionPolicy** | 无统一 policy 层 (AUTO/SAFE_AUTO/REVIEW_REQUIRED/MANUAL) |
| G7 | **Loop Protection** | 无组合总闸 (max_same_failure/max_same_decision/max_total_execution) |
| G8 | **Audit Correlation** | 无统一 correlation/execution_id 贯穿全链 |
| G9 | **生产状态模型统一** | 状态分散 (orchestrator/team_state), 需统一 STATUS 模型 |
| G10 | **Resume/Recovery 正式化** | 有基础 resume, 但 review→approve→resume 无正式接口 + 中断恢复测试 |
| G11 | **CLI 生产状态观察** | 无 factory status/budget/history/review/resume 命令 |

## 可复用 ✅

| 能力 | 复用方式 |
|---|---|
| AgentRuntime usage (execution_records) | Cost/Usage Record 数据源 |
| planning_trace token_usage | LLM planning 成本数据源 |
| max_replan/max_retry/max_auto_insert | Loop Protection 基础 |
| review_required 状态 + PlanCritic preflight | Review Gate 状态基础 |
| resume (跳过 completed) | Recovery 基础 |
| ProductionTrace | Audit Correlation 基础 |
| cost_profile (agents.py) | Agent 成本估算 |
| TaskDependencyGraph/Workspace/DecisionStore | 审计上下文 |

## 架构设计方向

```
ProjectBudget (G1) → BudgetEnforcer (G2) → CostLedger (G3/G4) → ReviewGate (G5)
ExecutionPolicy (G6) → LoopGuard (G7) → AuditCorrelation (G8) → StatusModel (G9)
Recovery/Resume (G10) → CLI 命令 (G11)

统一: 状态单一来源 / cost 单一来源 / decision 单一来源 (不引入第二套)
```

## 不该现在做 🚫

- 不重建 provider/cost 系统 (复用 execution_records + planning_trace)
- 不引入第二套状态/cost/decision 系统
- 不做 UI 大改 (CLI 命令 + 观察)
- 不破坏 S10-055~062 任何能力

---

> GAP 完毕 | G1-G11 缺失 | 复用充分 | 核心: 让自主生产"知道不能继续"→ STOP → EXPLAIN → WAIT → RESUME
