# S10-068 Part 2 — Autonomous Debug & Repair 架构设计

> 日期:2026-08-17 | Sprint: S10-068 Part 2 | 架构 (基于 GAP 分析 G1-G10)
> 原则: 复用 Part 1 + S10-063/067; 不重写; Core + CLI + API + -h + Tests 同交付

---

## 1. 完整闭环

```
FAILURE → ERROR UNDERSTANDING → ROOT CAUSE → MEMORY RETRIEVAL → FIX STRATEGY
  → REPAIR → VALIDATION → PASS → 成功
                    ↓ FAIL
                 再分析 (同根因?) → 换策略 (adaptation) → 再 Repair
                    ↓ 连续失败
                 LoopGuard/Budget → BLOCKED / WAITING_FOR_REVIEW
  → Memory Learning (经验沉淀) → Audit-ready Trace
```

## 2. DebugSession / DebugAttempt (debug_session.py)

```
@dataclass DebugAttempt:
  attempt_number / strategy / strategy_reason / validation_command /
  validation_result / status / timestamps / cost

@dataclass DebugSession:
  debug_id / project_id / task_id / agent_id / failure_id /
  error_summary / error_type / evidence / root_cause / root_cause_confidence /
  retrieved_experiences / selected_strategy / attempt_number /
  strategy_history (list) / validation_command / validation_result /
  status / budget_usage / timestamps / trace_id

状态: ANALYZING → ROOT_CAUSE_IDENTIFIED → STRATEGY_SELECTED → REPAIRING
  → VALIDATING → RETRYING → SUCCESS / BLOCKED / WAITING_FOR_REVIEW

class DebugSessionStore: create/update/get/list → debug_sessions.json (失败安全)
```

## 3. Strategy Adaptation (strategy_adaptation.py)

```
class StrategyAdapter:
  evaluate(attempt_result) -> bool (当前策略是否成功)
  next_strategy(session, available) -> FixStrategy
    (strategy_history 排除已失败策略; Memory 替代经验 → 新策略;
     全部策略失败 → REQUEST_REVIEW)
  history(session) -> list[{strategy, result}] (strategy_history 记录)
```

## 4. Repair Safety (repair_safety.py)

```
class RepairSafety:
  check(session, *, budget, loop_guard, policy, review_gate) -> (decision, reason)
    AUTO (预算充足 + 未超限 + policy 允许)
    SAFE_AUTO (轻度风险)
    REVIEW (budget review / loop 接近上限 / policy REVIEW)
    BLOCKED (budget block / loop block / 连续失败超限)
  复用 S10-063: BudgetEnforcer/LoopGuard/ExecutionPolicy/ReviewGate
```

## 5. DebugRetrievalPolicy (retrieval_policy.py)

```
class DebugRetrievalPolicy:
  build_query(session) -> str (error + task + project 特征)
  select_sources(session) -> list (debug_experience 优先 + project 经验)
  retrieve(session, memory_store, top_k) -> candidates
  rank(candidates) -> 排序 (项目相关 > confidence > 新鲜 > 成功 > 已验证)
  deduplicate(candidates) -> 去重
  apply_budget(candidates, max_tokens) -> (selected, stats)
    stats: candidates_count/selected_count/discarded_count/estimated_tokens/max_tokens/latency
  → 未来多 RAG 来源扩展点 (select_sources 可扩展)
```

## 6. Context Budget (context_budget.py)

```
class ContextBudget:
  estimate_tokens(text) -> int
  fit(records, max_tokens) -> list (Top-K + 截断保 max_tokens)
  stats(...) -> {candidates_count, selected_count, discarded_count,
                 estimated_tokens, max_tokens, latency}
```

## 7. DebugTrace (debug_trace.py)

```
class DebugTrace:
  record(session, *, fallback, governance, cost, tokens, latency)
  → debug_trace.json (Audit-ready: 为什么修/谁修/用了什么经验/为什么换策略/花了多少钱)
```

## 8. DebugPipeline (debug_pipeline.py)

```
class DebugPipeline:
  start(project_id, task_id, agent_id, error_message) -> DebugSession
  analyze(session) -> session (classify + root_cause + retrieve + strategy)
  repair(session, *, workspace, budget, loop_guard, policy, review_gate) -> session
    (RepairSafety.check → AUTO: 执行修复 (RepairManager 薄调) / REVIEW: 请求审批 / BLOCKED: 停)
  validate(session, *, validation_command) -> session (PASS→SUCCESS / FAIL→RETRYING)
  adapt(session) -> session (strategy_history + 替代策略)
  run(session, *, max_attempts=3) -> session (完整闭环: analyze→repair→validate→adapt 循环)
  resume(session, *, decision) -> session (REVIEW 通过后继续)
  learn(session) -> None (成功/失败 → Memory 沉淀 + DebugTrace)
  CLI→Core→API 同一入口
```

## 9. Root Cause 分类增强 (root_cause.py 扩展)

```
ROOT_CAUSE_TYPES: CODE_DEFECT/TEST_DEFECT/REQUIREMENT_MISMATCH/ENVIRONMENT_FAILURE/
  DEPENDENCY_FAILURE/CONFIGURATION_FAILURE/DATA_FAILURE/INTEGRATION_FAILURE/UNKNOWN
RootCause 增加: root_cause_type + reasoning_summary
LLM 可语义理解 → Deterministic Validation → Governance → Execution
```

## 10. CLI (session/actions.py + intent.py)

```
factory debug session   — "开始调试"/"调试会话"
factory debug analyze   — "分析这个错误"/"为什么失败" (已有)
factory debug root-cause — "找一下根因" (新)
factory debug recommend — "给我修复建议" (已有)
factory debug repair    — "自动修复" (新)
factory debug validate  — "验证修复" (新)
factory debug resume    — "继续调试" (新)
factory debug history   — "查看调试历史" (已有)
factory debug stats     — "debug统计" (已有)
-h: 全注册 + intent 关键词 ("自动修复"/"验证修复"/"继续调试"/"找一下根因"/"开始调试")
```

## 11. API (api/debug.py 扩展)

```
POST /api/debug/session    — 开始会话
POST /api/debug/analyze    — 分析 (已有)
POST /api/debug/root-cause — 根因 (新)
POST /api/debug/recommend  — 推荐 (已有)
POST /api/debug/repair     — 修复 (新)
POST /api/debug/validate   — 验证 (新)
POST /api/debug/resume     — 继续 (新)
GET  /api/debug/history    — 历史 (已有)
GET  /api/debug/stats      — 统计 (已有)
CLI 与 API 调用同一 Core (DebugPipeline)
```

## 12. 测试计划 (100+)

```
Core (>=50): Session 状态机/Adaptation/RetrievalPolicy/ContextBudget/Trace/RootCause 分类
CLI (>=15): 9 命令 + intent
API (>=20): 9 端点
Governance (>=10): LoopGuard/Budget/Review 约束 Debug
Integration (>=15): 真实 E2E 4 场景 (A: 修复PASS / B: 换策略PASS / C: BLOCKED / D: fallback)
```

## 13. 边界

- 不重写 Part 1/S10-063/S10-067 (复用)
- 不引入 Vector DB/完整 RAG (接口预留)
- Repair 用 RepairManager 现有执行 (不造新执行引擎)
- 不绕过 Governance (RepairSafety 强制)

---

> 架构完毕 | DebugSession + Pipeline + Adaptation + Safety + RetrievalPolicy + Trace + CLI + API
