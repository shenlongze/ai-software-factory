# 02 — EXPERIENCE DOMAIN (P2-C CONTRACT, 2026-09-06)

## 1. Canonical Experience (冻结)

- entity: ExperienceRecord (保留现有 model, 扩展字段)
- id: **exp-{hex12} 保留** (现有 84 条已用; 不 rename 不迁移 — 对齐 P0 原则)
- store: memory/experience_store.json (唯一 canonical SSOT)
- 不可变核心: provenance (task_run_id/exs_id/release_id) 一旦建立不改

## 2. Schema 扩展 (未来 Implementation 加)

```
现有: id/type/source/success/task/project/agent/role/problem/action/result/
      confidence/context/created_at
新增 (provenance anchor, 可空):
  task_run_id   run-*      (P0)
  exs_id        EXS-*      (P0)
  release_id    RELEASE-*  (P2-A, 可选)
source_id       (确定性来源引用 — 幂等键基础)
```

## 3. Experience type (语义分类 — 现有 4 type 足够, 不加新 type)

现有 type 已覆盖: SUCCESS_PATTERN (成功执行) / FAILURE_PATTERN (失败) /
DEBUG_EXPERIENCE (修复) / PLANNING_EXPERIENCE (规划)。来源用 source 区分
(execution/release/recovery)。**不加新 type 枚举** (经 provenance 区分来源)。

## 4. 不区分 "Execution vs Release Experience" 为两个事实

同一 (task_run, exs) 的执行经验 = 一条; RELEASE 只**附加 release_id** 到已有
执行经验 或 对纯 release 决策 (REJECTED/REVOKED) 建独立 release 经验 —
见 08。
