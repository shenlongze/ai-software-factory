# 06 — VERSIONING CONTRACT (P1 CONTRACT, 2026-09-05)

> D7: PRD/Requirement/Plan 版本语义

---

## 1. 冻结

| Entity | 版本需要? | 语义 |
|---|---|---|
| PRD | **是 (最重要)** | PRD entity 不可变版本; 每次 approved 生成新 version。Task/Plan 引用 **PRD version id** (PRD-xxx@v2), 非裸 PRD entity — 保证执行针对的文档内容可追溯 |
| Requirement | 是 (轻量) | 状态流转 (draft→validated→approved→superseded); superseded 保留历史, 不改原记录内容 (不可变) |
| Plan | **否 (immutable snapshot)** | Plan 是审批通过的快照; 修改 = 新 Plan (新 PLAN-*), 不 UPDATE |
| Idea/Discovery | 否 | created 后不可变核心字段; 状态流转 |

## 2. 关键决策

**Task 引用 PRD version 还是 PRD entity?**
→ Task → Plan → PRD version (plan.prd_version_ref = PRD-xxx@vN)。Task 本身只挂
plan_id (P0 contract 不动); PRD version 经 Plan 可达。

**Plan immutable snapshot 还是 mutable entity?**
→ immutable snapshot (现状 plan 生成后 ask_approval=true 即不再改);
修改需求 → 新 Plan (计划迭代)。

## 3. PRD 三层边界

```
PRD-* entity (truth: 结构化字段) 
   ↓ 每 approved 版本
PRD version (versioned snapshot: version_id, content_ref)
   ↓ 投影
PRD.md (document projection — 可再生, 非 truth)
```

Document 与 Truth 关系见 07。
