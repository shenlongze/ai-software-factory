# S10-068 — GAP ANALYSIS (Part 1)

> 日期:2026-08-17 | Sprint: S10-068 | P0 现状审查
> 目标: Repair Loop → Debug Intelligence (理解错误→根因→历史经验→修复策略)

---

## 核心问题回答

### 1. 当前 Repair Loop 可以解决什么?
```
RepairManager (quality.py):
  create_repair(task) → repair_task.json → Agent 重跑 → 验证重跑
  解决: "任务本身失败" (重试语义, max_retry 限制, 不无限重试)
✅ 能处理: 单次失败 → retry/repair 闭环
```

### 2. 为什么它不是 Debug Intelligence?
```
Repair Loop = 失败 → 重试 (不分析原因)
Debug Intelligence = 失败 → 理解错误 → 根因分析 → 历史经验检索 → 修复策略 → 修复

差距:
  ❌ 不理解错误 (error 只是字符串)
  ❌ 不分析根因 (为什么失败?)
  ❌ 不利用历史经验 (S10-067 Memory 未接入)
  ❌ 不选择修复策略 (FIX_CODE/FIX_TEST/CHANGE_DESIGN/ROLLBACK/REQUEST_REVIEW)
  ❌ 无学习反馈 (修复结果未沉淀回 Memory)
```

### 3. 当前缺少什么?
| 能力 | 现状 | 缺 |
|---|---|---|
| Error Understanding | error 字符串透传 | DebugCase 模型 (error_type/message/stack_trace/context) |
| Root Cause Analysis | 无 | RootCause (cause/evidence/confidence) |
| Debug Memory Retrieval | Memory 有 recommend_for_debug 但未接入 Debug | DebugExperienceRetriever (Top-K + Ranking) |
| Fix Strategy Decision | 无 | FixStrategy 枚举 + DebugDecision |
| Experience Feedback Loop | Memory 有提取但 Debug 不主动写 | 修复结果 → 新经验沉淀 |

### 4. Memory Learning 当前能力如何复用?
```
✅ ExperienceRetriever.search (S10-067): 关键词/类型/项目过滤 + confidence 排序
✅ Recommender.recommend_for_debug (S10-067): 问题关键词 → 历史调试经验
✅ ExperienceStore: DEBUG_EXPERIENCE 类型已存在
✅ LearningTrace: 学习审计

复用方式: DebugEngine → DebugExperienceRetriever → ExperienceRetriever.search(DEBUG_EXPERIENCE)
→ Top-K 排序 → 修复策略推荐; 修复结果 → ExperienceStore.add (Feedback Loop)
```

## GAP 汇总

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **DebugCase 模型** | error_type/message/stack_trace/task_id/agent_id/affected_files/context/previous_attempts |
| G2 | **RootCause 分析** | cause/evidence/confidence + related_experience |
| G3 | **FixStrategy 枚举** | FIX_CODE/FIX_TEST/CHANGE_DESIGN/ROLLBACK/REQUEST_REVIEW |
| G4 | **DebugDecision** | strategy/reason/confidence/evidence |
| G5 | **DebugExperienceRetriever** | Memory Top-K 检索 + Ranking + Context (未来 Embedding/Hybrid 接口) |
| G6 | **DebugEngine** | DebugCase → DebugDecision (规则 + Memory + LLM 可选) |
| G7 | **CLI/API** | factory debug analyze/history/recommend/stats + 4 API 端点 |
| G8 | **Repair Loop 接入** | 失败 → DebugEngine → Decision → Repair Loop (不替换, 提供 recommendation) |

## 可复用 ✅

```
S10-067 Memory: ExperienceRetriever/ExperienceStore/DEBUG_EXPERIENCE/LearningTrace
RepairManager (quality.py): 修复执行基础
ReasoningProvider (S10-062): LLM 可选 (根因/策略生成)
actions 注册 + api/ 路由模式: CLI/API
```

## 架构方向

```
session/debug/ (新增):
  debug_engine.py      — DebugEngine 主入口 (DebugCase → DebugDecision)
  error_analysis.py    — 错误理解 (error → error_type)
  root_cause.py        — 根因分析 (error + context → RootCause)
  debug_strategy.py    — 修复策略选择 (root_cause + memory → FixStrategy)
  debug_memory.py      — DebugExperienceRetriever (Memory Top-K + Ranking)

CLI: factory debug analyze/history/recommend/stats
API: POST /api/debug/analyze, /api/debug/recommend, GET /api/debug/history, /api/debug/stats
接入: Repair Loop (失败 → DebugEngine → recommendation, 不替换旧逻辑)
```

## 不该现在做 🚫 (Part 1 范围控制)

```
Web UI / 自动代码修改 Agent / 完整 LLM Debug Reasoning / Vector Database
```

---

> GAP 完毕 | G1-G8 缺失 | Memory 可复用 | 范围: Debug Intelligence 基础 (非完整 LLM Debug)
