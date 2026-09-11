# 03 — D3 RELATIONSHIP CONTRACT (P0-F4 DECISION, 2026-09-05)

> D3 = APPROVED: 多对多 FK 契约 (非简单 1:1 链)

---

## 1. 冻结决策

**不是** Artifact → Verification → Evidence 的单向 1:1 记录链。
真实模型允许多对多:

```
一个 TaskRun → 多个 Artifact
一个 TaskRun → 一个或多个 Verification
一个 Verification → 检查多个 Artifact
一个 Verification → 多个 Evidence
一个 Artifact → 被多个 Verification 检查
一个 Evidence → 被多个 Verification 引用 (共享)
```

## 2. Canonical 关系图

```
Task (TASK-*)
  ↓
TaskRun (run-*)
  ├── Artifact[] (art-*)
  ├── Verification[] (ver-*)      ← F3
  └── EXS (EXS-*)
        └── (Artifact 引用 exs_id)
Verification (ver-*) ↔ Artifact[] (art-*)   ← 多对多 (F4 impl)
Verification (ver-*) → Evidence[] (EVD-*)   ← F4 impl
```

## 3. 最低字段要求 (F4 impl 冻结依据)

**Artifact (S2 扩展):**
```
artifact_id      art-*        (已有)
task_run_id      run-*        (已有 = node_run_id)
exs_id           EXS-*        (新增可选参数, 向后兼容)
artifact_type    (已有)
lifecycle_state  (已有)
content/location reference     (已有: payload/patch_text/workspace)
```

**Verification (F3 已有, 补充):**
```
verification_id  ver-*        (已有)
task_run_id      run-*        (已有)
exs_id           EXS-*        (已有)
status           PASS/FAIL/UNKNOWN (已有)
verifier metadata              (已有: method/type/actor)
evidence references             (已有 evidence_ref[], F3 预留 — F4 impl 指向 EVD-*)
```

**Evidence (新 EVD-*):**
```
evidence_id      EVD-*
verification_id  ver-*        (可空 — 允许未挂 verification 的独立证据? F4 impl 定)
evidence_type
source/reference
supporting data
created_at / actor             (provenance)
immutable
```

## 4. FK 方向总结

- art.task_run_id → run-* (已有 node_run_id; 重命名/别名兼容)
- art.exs_id → EXS-* (新增)
- ver.task_run_id / ver.exs_id → 已有 (F3)
- ver.evidence_ref[] → EVD-* (F3 预留, F4 impl 填充)
- ver ↔ art: 多对多 (F4 impl 定 join — 建议 ver.artifact_refs[] 或 art.verification_refs[];
  选一方向, F4 impl 决策点 — 推荐 ver.artifact_refs[] 保持 artifact 纯净)
- EVD.verification_id → ver-* (创建时绑定)

## 5. 禁止

- Artifact→Verification→Evidence 单向 1:1 链
- 用单一 "file" 对象同时充当 Artifact/Verification/Evidence
- EXS/audit/filename 隐式关系代替 FK
