# S10-068 — Debug Intelligence (Part 1)

> 日期:2026-08-17 | Sprint: S10-068 | Debug Intelligence & Reasoning System
> 状态: Repair Loop → Debug Intelligence (理解错误→根因→历史经验→修复策略)

---

## 1. 核心闭环

```
生产 → 失败 → Debug Intelligence → 历史经验 → 修复策略 → Repair → 成功经验沉淀 → Memory
```

## 2. Capability Delivery

```
Core:
✅ DebugCase (error_type/message/stack_trace/task/agent/affected_files/context/previous_attempts)
✅ ErrorAnalyzer (9 类错误分类: TIMEOUT/IMPORT_ERROR/ASSERTION/AUTH/API_CONTRACT/NULL/MISSING/TEST_FAILURE/UNKNOWN)
✅ RootCauseAnalyzer (根因假设 + evidence + confidence + 经验置信度加成)
✅ DebugExperienceRetriever (Memory Top-K + confidence 排序 + 去重; 接口预留 embedding/hybrid)
✅ DebugStrategySelector (7 规则: UNKNOWN→REQUEST_REVIEW / 成功经验→FIX_CODE /
   TEST_FAILURE→FIX_TEST / API_CONTRACT→CHANGE_DESIGN / attempts>=2→ROLLBACK)
✅ DebugEngine (analyze 全流程 + feedback 循环 + history + stats + debug_cases.json)
✅ Feedback Loop (success→SUCCESS_PATTERN, fail→FAILURE_PATTERN → Memory 沉淀)

CLI:
✅ debug_analyze    — "分析错误"/"为什么失败"/"debug" → DebugDecision
✅ debug_history    — "查看调试经验"/"debug历史"
✅ debug_recommend  — "修复建议"/"debug推荐"
✅ debug_stats      — "debug统计"
-h: ✅ action metadata + 4 新意图关键词

API:
✅ POST /api/debug/analyze   — {error_message, task_id?, agent_id?, context?} → DebugDecision
✅ POST /api/debug/recommend — → 策略推荐
✅ GET  /api/debug/history   — → [DebugCase]
✅ GET  /api/debug/stats     — → 统计
schema: ✅ Pydantic + error handling; 注册: ✅ api/__init__.py

Tests:
✅ Core: 41 | CLI: 20 | API: 19 = 80 新测试 (四覆盖)
```

## 3. 真实验证 (ScorePocket Memory + 真实失败)

```
失败: "pytest failed: 计分 API 实现失败 expected score 10 got 9"
  1. Memory 检索: DebugEngine 内部命中 1 条相关经验 (计分 API 成功经验)
  2. DebugEngine 决策: TEST_FAILURE → 策略 FIX_CODE (有历史成功经验 → 修复代码)
     —— 策略随历史经验变化 (无经验时 FIX_TEST → 有经验 FIX_CODE) = Debug Intelligence 核心
  3. Feedback Loop: 修复成功 → Memory 沉淀 (+1 SUCCESS_PATTERN, 总数 50)
```

## 4. 修复的真实缺陷

- api/debug.py import DebugEngine 失败 → 包 __init__ 惰性导出
- feedback(outcome) 仅接受字符串, dict 被 str() → outcome 兼容 (dict: {"success": True})
- _update_outcome 匹配条件 ("" / "pending") 未匹配 → 修正

## 5. 测试

```
新增: 80 (Core 41 + CLI 20 + API 19)
全量: 11317 passed + 1 skipped, 0 failed (11237 基线 → +80, 零回归)
```

## 6. 技术债 (Part 2 计划)

- 无完整 LLM Debug Reasoning (规则为主, LLM 接口预留)
- Repair Loop 未自动接入 DebugEngine (Part 1 只提供 recommendation)
- 无 Vector DB (retrieval 接口预留 embedding/hybrid)
- 无自动代码修改 Agent

## 7. 下一 Sprint 建议

```
S10-069 — Audit Intelligence (企业级审计: Who/What/When/Why/Impact/Approval)
  Debug 决策可审计: 为什么这样修? 用了什么经验? 谁批准的?
```

---

> S10-068 Part 1 文档完毕 | Debug Intelligence 基础 | 80 新测试 | 11317 全绿
