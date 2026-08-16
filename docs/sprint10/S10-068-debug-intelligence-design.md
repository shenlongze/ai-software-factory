# S10-068 — Debug Intelligence 架构设计 (Part 1)

> 日期:2026-08-17 | Sprint: S10-068 | 架构 (基于 GAP 分析 G1-G8)
> 范围: Debug Intelligence 基础 (非完整 LLM Debug) — Core + CLI + API + Tests

---

## 1. 架构

```
失败 (pytest/validation/agent error)
              ↓
┌──────────────────────────────────────────────┐
│ DebugEngine (debug_engine.py)                │
│   DebugCase → DebugDecision                  │
│   1. error_analysis (错误理解)               │
│   2. root_cause (根因分析)                   │
│   3. debug_memory (历史经验检索)             │
│   4. debug_strategy (修复策略选择)           │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ Repair Loop (quality.py 已有, 不替换)         │
│   DebugDecision.recommendation → 修复执行    │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ Memory (S10-067) — 修复结果 → 新经验沉淀     │
└──────────────────────────────────────────────┘
```

## 2. Core 数据模型 (session/debug/__init__.py)

```
@dataclass DebugCase:
  error_type / error_message / stack_trace / task_id / agent_id /
  affected_files / context / previous_attempts / project

@dataclass RootCause:
  cause / evidence / confidence / related_experience

class FixStrategy (枚举):
  FIX_CODE / FIX_TEST / CHANGE_DESIGN / ROLLBACK / REQUEST_REVIEW

@dataclass DebugDecision:
  strategy / reason / confidence / evidence / related_experiences
```

## 3. error_analysis.py

```
class ErrorAnalyzer:
  classify(error_message, stack_trace) -> error_type
  规则: 关键词 → 类型 (timeout→TIMEOUT; import/module→IMPORT_ERROR;
    assert→ASSERTION; key/credential→AUTH; api/contract→API_CONTRACT;
    memory/None→NULL; 缺→MISSING; 等) + unknown 兜底
  extract(error_message, stack_trace) -> DebugCase
```

## 4. root_cause.py

```
class RootCauseAnalyzer:
  analyze(debug_case, related_experiences) -> RootCause
  规则: error_type + message 关键词 → 根因假设 (evidence = 匹配关键词/经验)
  例: API_CONTRACT + "missing field" → "API 契约缺失字段"
  可选 LLM: llm_provider → 结构化根因 (失败 → 规则兜底)
```

## 5. debug_memory.py

```
class DebugExperienceRetriever:
  retrieve(debug_case, *, top_k=3, memory_store=None) -> list[ExperienceRecord]
    → ExperienceRetriever.search(query=error_message/task, type=DEBUG_EXPERIENCE/FAILURE_PATTERN)
    → Top-K 排序 (confidence 降序) + 去重
  接口预留: 未来 embedding/hybrid (retrieve 签名不变, 实现可换)
```

## 6. debug_strategy.py

```
class DebugStrategySelector:
  select(root_cause, related_experiences, debug_case) -> DebugDecision
  规则:
    - REQUEST_REVIEW: 高 confidence 无经验/高风险 (错误未分类/未知)
    - FIX_CODE: 历史经验成功 (SUCCESS_PATTERN/DEBUG 且 confidence 高)
    - FIX_TEST: 验证失败 (assertion/test 相关)
    - CHANGE_DESIGN: 架构/契约问题 (API_CONTRACT + 无直接修复)
    - ROLLBACK: 重复失败 (previous_attempts >= 2)
  可选 LLM: llm_provider → 策略生成 (失败 → 规则兜底)
```

## 7. debug_engine.py

```
class DebugEngine:
  analyze(debug_case, *, llm_provider=None, memory_store=None) -> DebugDecision
    (完整流程: classify → root_cause → retrieve → strategy)
  feedback(debug_case, decision, outcome, workspace) -> None
    (修复结果 → Memory: success → SUCCESS_PATTERN; fail → FAILURE_PATTERN — Feedback Loop)
  history(workspace, limit=20) -> list (debug_cases 历史)
  stats(workspace) -> dict (按 error_type/strategy 统计)
  持久化: debug_cases.json
```

## 8. API (api/debug.py)

```
POST /api/debug/analyze   — {error_message, task_id?, agent_id?, context?} → DebugDecision
POST /api/debug/recommend — {error_message} → 策略推荐 (同 analyze 简版)
GET  /api/debug/history   — → [DebugCase]
GET  /api/debug/stats     — → 统计
纯函数路由 + Pydantic + error handling + 注册 api/__init__.py
```

## 9. CLI (session/actions.py + intent.py)

```
factory debug analyze   — "分析错误"/"debug"/"为什么失败" → DebugDecision
factory debug history   — "查看调试经验" → 历史
factory debug recommend — "修复建议" → 策略推荐
factory debug stats     — "debug统计" → 统计
-h: action metadata + intent 关键词
```

## 10. Repair Loop 接入

```
失败 → DebugEngine.analyze (提供 recommendation) → Repair Loop 保持旧逻辑
第一阶段的"接入": DebugEngine 可独立调用 + RepairManager 可选接收 decision
(不替换 Repair Loop — Part 1 范围)
```

## 11. 测试计划 (>=80)

```
Core (>=45): DebugCase/RootCause/FixStrategy/DebugDecision/ErrorAnalyzer/
  RootCauseAnalyzer/DebugExperienceRetriever/DebugStrategySelector/DebugEngine/
  feedback 循环/持久化
CLI (>=15): 4 命令 + intent 关键词
API (>=15): 4 端点 + schema + error handling
Integration (>=10): 真实失败案例 (错误→分析→Memory 检索→策略→反馈)
```

## 12. 边界

- 不替换 Repair Loop (提供 recommendation)
- 不引入 Vector DB (接口预留)
- 复用 S10-067 Memory + S10-062 ReasoningProvider (可选 LLM)
- 完整 LLM Debug Reasoning → Part 2+

---

> 架构完毕 | DebugEngine 5 模块 + CLI + API | Debug Intelligence 基础
