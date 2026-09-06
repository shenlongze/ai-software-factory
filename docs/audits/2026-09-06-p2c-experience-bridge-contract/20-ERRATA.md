# 20 — ERRATA (P2-C CONTRACT, 2026-09-06)

> 勘误记录 — Q14/Q15 补充审计发现 (READ-ONLY 期间新增, 不改已冻结 00-19)

---

## 1. 勘误 1: intelligence/experiences.json 计数错误

**原记录** (12-SSOT-MULTI-LEDGER-AUDIT.md):
```
intelligence/experiences (空壳 1)
```

**实际**: `intelligence/experiences.json` 含 **85 条** (顶层 `{"experiences": {...}}`
嵌套 dict, 前序按顶层 len 误判为 1; 内嵌实际 85, 时间 2026-08-14 ~ 08-18)。

**性质**:
- 归属: factory-core/intelligence 域 (`intelligence/store.py` _JsonRecordStore,
  独立 `_filename=experiences.json` / `_section=experiences`)
- schema: domain/subject_id/subject_type/task_type/capability/quality_score/
  cost/duration/result/evidence/freshness/confidence/last_used
- id: uuid (非 exp-*)
- consumer: factory-core/cli commands (product/intelligence 审批域);
  factory-console 零读取
- 时间/内容: M3 时代 agent capability tracking (task_type=T001-T007/
  task-e1-*/task-client-ui 等 M3 执行域)

**判定**: 独立历史体系 (factory-core intelligence), 与 factory-console memory
experience_store (exp-* 84) 不同域/不同 schema/不同 id/不同消费者 — 非同一
事实的竞争 canonical; = **LEGACY (S9/intelligence 域)**, P2-C 不并入不迁移。

## 2. 勘误影响: Implementation Scope 增补

P2-C Implementation IN SCOPE 增 1 项:
- intelligence/experiences.json (85) 显式标 **LEGACY 隔离** — 确保无代码把
  它当 canonical Experience (不改不迁移, 只记录边界 + 防止误读)。

P2-C canonical Experience 目标不变:
- exp-* (memory/experience_store.json) = 唯一 canonical
- ExperienceBridge = 唯一 writer
- (source, source_id) 幂等 / anchor FK / 单向派生契约 — 全部维持

## 3. Q14 最终结论

存在两个 Experience-like 域, 但**不构成竞争 canonical SSOT**:
memory exp-* (console 域, canonical 目标) vs intelligence experiences
(core 域, LEGACY)。无 STOP-4。

## 4. Q15 最终结论

**GO** (契约级, 含本勘误条件) — 12-SSOT 文档计数已修正; Implementation
scope 已增 legacy 隔离项; 其余 GO 条件全部可冻结。
