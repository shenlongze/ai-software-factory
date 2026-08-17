# S10-068 Part 2 — GAP ANALYSIS

> 日期:2026-08-17 | Sprint: S10-068 Part 2 | P0 现状审查
> 目标: Debug Intelligence → Autonomous Debug & Repair (受治理约束的自主修复)

---

## 一、Part 1 能力边界

```
✅ DebugEngine: analyze (classify→root_cause→retrieve→strategy) / feedback / history / stats
✅ ErrorAnalyzer: 9 类错误分类
✅ RootCauseAnalyzer: 根因假设 + evidence + confidence
✅ DebugExperienceRetriever: Memory Top-K + 排序
✅ DebugStrategySelector: 7 规则 (FIX_CODE/FIX_TEST/CHANGE_DESIGN/ROLLBACK/REQUEST_REVIEW)
✅ Feedback Loop: success→SUCCESS_PATTERN, fail→FAILURE_PATTERN
✅ CLI: 4 action + API: 4 端点 (analyze/recommend/history/stats)
```

**Part 1 只提供 recommendation — 不执行 Repair。**

## 二、5 个 CASE 场景审查

| CASE | 需求 | 现状 | GAP |
|---|---|---|---|
| CASE 1 | 失败→分析→根因→经验→策略→修复→测试→PASS | 分析/策略有; **无修复执行/验证循环** | G1 |
| CASE 2 | 第一次修复失败→分析新失败→换策略→再修复 | **无 strategy adaptation** | G2 |
| CASE 3 | 连续失败→LoopGuard/Retry Limit/Budget→BLOCKED/REVIEW | Governance 有(S10-063); **Debug 未接入** | G3 |
| CASE 4 | LLM 不可用→deterministic fallback→安全 | Part 1 有规则兜底; **无统一 fallback 链** | G4 |
| CASE 5 | 修复成功→Validation PASS→经验提取→Memory→LearningTrace | Feedback 有; **无 Validation 集成 + Trace** | G5 |

## 三、GAP 汇总

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **DebugSession/DebugAttempt** | 统一 Pipeline 状态机 (ANALYZING→ROOT_CAUSE→STRATEGY→REPAIRING→VALIDATING→RETRYING→SUCCESS/BLOCKED/REVIEW) + 持久化 |
| G2 | **Strategy Adaptation** | strategy_history: 失败策略不再重复, 从 Memory 换替代策略 |
| G3 | **Repair Safety (Governance 接入)** | Budget/Cost/Retry limit/LoopGuard/Policy/ReviewGate 约束 Debug 执行; AUTO/SAFE_AUTO/REVIEW/BLOCKED 决策 |
| G4 | **Fallback 链** | LLM→deterministic→REVIEW/BLOCKED (统一) |
| G5 | **Validation Loop** | repair 后验证: PASS→SUCCESS; FAIL→再分析 (不无限重试) |
| G6 | **DebugRetrievalPolicy** | 查询构建/来源选择/Top-K/重排/去重/Context Budget (未来多 RAG 扩展点) |
| G7 | **Context Budget** | candidates/selected/discarded/estimated_tokens/max_tokens/latency (不让 Memory 全量进 LLM) |
| G8 | **DebugTrace** | Audit-ready: failure/root_cause/evidence/retrieval/strategy/attempt/validation/result/fallback/governance/cost/tokens/latency |
| G9 | **Root Cause 分类增强** | CODE_DEFECT/TEST_DEFECT/REQUIREMENT_MISMATCH/ENVIRONMENT/DEPENDENCY/CONFIGURATION/DATA/INTEGRATION/UNKNOWN |
| G10 | **CLI/API 执行链** | session/analyze/root-cause/recommend/repair/validate/resume + history/stats; CLI→Core→API 同一逻辑 |

## 四、可复用 ✅

```
S10-068 Part 1: DebugEngine/ErrorAnalyzer/RootCauseAnalyzer/DebugStrategySelector/DebugExperienceRetriever/feedback
S10-063: LoopGuard/BudgetEnforcer/ReviewGate/ExecutionPolicy (Governance 约束)
S10-067: ExperienceStore/ExperienceExtractor/PatternLearner/LearningTrace (Memory 闭环)
quality.py: RepairManager (修复执行)
orchestrator: validation (测试执行)
```

## 五、架构方向

```
session/debug/ 新增:
  debug_session.py   — DebugSession/DebugAttempt 状态机 + 持久化 (debug_sessions.json)
  debug_pipeline.py  — DebugPipeline: 完整闭环 (analyze→repair→validate→adapt→learn)
  strategy_adaptation.py — Strategy Adaptation (strategy_history + 替代策略)
  repair_safety.py   — Governance 接入 (Budget/LoopGuard/Policy/ReviewGate → AUTO/SAFE_AUTO/REVIEW/BLOCKED)
  retrieval_policy.py — DebugRetrievalPolicy (查询/来源/Top-K/重排/去重/Context Budget)
  debug_trace.py     — DebugTrace (Audit-ready 记录)

CLI (新增 4): debug session / repair / validate / resume (+ 已有 4)
API (新增 5): POST /api/debug/session, /repair, /validate, /resume, /root-cause
```

## 六、测试计划 (100+)

```
Core (>=50): Session 状态机/Adaptation/Repair Safety/Retrieval Policy/Context Budget/Trace
CLI (>=15): 8 命令 + intent
API (>=20): 9 端点
Governance (>=10): LoopGuard/Budget/Review 约束
Integration + E2E (>=15): 4 真实场景 (A: 修复PASS / B: 换策略PASS / C: BLOCKED / D: fallback)
```

## 七、不该现在做 🚫

```
完整 Multi-RAG 平台 (接口预留)
自动代码修改 Agent (Repair 用 RepairManager 现有执行)
Vector DB (retrieval 接口预留)
```

---

> GAP 完毕 | G1-G10 缺失 | Part 1 + S10-063/067 可复用 | 完整 Autonomous Debug & Repair
