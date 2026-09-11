# 04 — LEARNING AUDIT (P2 GAP AUDIT, 2026-09-06)

## L1 Experience
exp-* (ExperienceStore, memory/experience_store.json) — **84 条真实**。
schema: action/agent/confidence/context/problem/project/result/role/source/success/task/type。
type: SUCCESS_PATTERN 48 / DEBUG 21 / FAILURE_PATTERN 10 / PLANNING 5。

## L2 Production→Experience 桥 (REAL)
extraction.py: EXECUTION_RECORDS_FILE (exec/execution_records.json = **P0 EXS**) →
提取 SUCCESS/FAILURE_PATTERN。真实 exp 的 source: execution_records 55 (真桥!)
+ repair_task 18 + replanning 3 + validation 3。
AutoLearner (orchestrator M3 触发) → extract→store→trace。

## L3 Experience→Learning 引擎
learning_engine.py (PatternLearner/learn_agent) + learning_engine_v2 (observation/
candidate/hypothesis, <root>/intelligence/) — 代码完整。
**真实数据: observations/candidates/hypotheses 0 文件** (intelligence/ 仅
decisions/experiences/recommendations 各 1 空壳)。
learning_trace.json 840 条 (learning_engine.run 审计, 曾运行过)。

## L4 Learning Consumption (关键缺口)
refresh_agent_profiles (经验→PatternLearner.learn_agent→agent_profiles.json) →
load_agent_profiles → CapabilityRouter (路由排序) — **代码闭环通**。
**但 agent_profiles.json 真实文件 0** — refresh 从未真实运行 (仅 actions_memory
手动触发)。→ 消费代码在, 无真实 learned 数据流入。

## L5 Provenance
exp 有 source/task/project (溯源 OK); learning_trace 840 有 source/impact。
但 learning 产物 (profile/pattern) 未落盘 → 无法证明影响任何 run。

## 结论
LEARNING = M2 (Experience REAL + 引擎 REAL; consumption 桥代码通但零真实数据闭环)。
