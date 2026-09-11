# 10 — LEGACY BOUNDARY (P1 CONTRACT, 2026-09-05)

> D16 + D19: 历史数据不迁移不伪造

---

## 1. 冻结分类

| 历史对象 | 分类 | 处置 |
|---|---|---|
| PI-* (S9 ideas, 2 测试) | LEGACY | 保留 S9 域; 不并入 IDEA-* 链; 不迁移 |
| req_{hex12} (7 条) | LEGACY | 保留原样; 新链 REQ-*; 不转换语义 |
| 旧 PLAN-* (存 3 处快照) | LEGACY-CURRENT | 现有计划保留; 新 Plan 进 plans store; 不重写历史 |
| PRD.md (6) | LEGACY document | 保留; 新 PRD-* + 投影 |
| session_plans / session_topics / console_sessions | ORCHESTRATION STATE | 保留会话历史; 新链不依赖 |
| M3 legacy 项目 (execution_plan/tasks.json) | LEGACY | 隔离 |
| 历史 TASK-* 无 provenance | LEGACY | 不 backfill FK |
| DISCOVERY_CONFIRMED events | EVENT (观察) | 非 domain; 不重建 |
| product.json (M3 status=development) | LEGACY | 不并入 |

## 2. BRIDGE REQUIRED (仅契约, 不实现)

- 旧 Web create_feature "idea" 语义 → 新 IDEA-* (行为改, 历史 feature 保留任务树)
- 现有 requirements.json schema → REQ-* (同文件升级或新文件 — P1 Impl 决策)

## 3. P1 Implementation 默认

只保证**新链路**产生 canonical truth; 旧数据 = LEGACY / HISTORICAL TRUTH,
不动不改不转换。
