# 05 — EVIDENCE ID LEDGER (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

---

## 1. 单套账本

| 项 | 值 |
|---|---|
| ID | ev-{uuid4.hex[:8]} (EvidenceBundle.bundle_id) |
| 持久化 | projects/{slug}/evidence/ev-*.json (EvidenceStore) |
| 写者 | EvidenceBuilder (repo_mode) / orchestrator (M3) / EvidenceStore.save |
| 读者 | CLI (evidence list/show) / backlog_sweeper / task_tree |
| task_id | 旧 slug (ai-factory) — M3 |
| artifacts 引用 | 空 (0/9) |
| test_results | 空 (0/9) |

## 2. 与 canonical 链

```
ev-* ── task_id (旧 slug) ─► M3 legacy (非 TASK-*)
ev-* ── artifacts[] ───────► 空 (不指向 art-*/ART-*/EXS patch)
ev-* ── ? ────────────────► ver-* (F3): 无引用
```

## 3. 单套 = 无多 SSOT 冲突

Evidence 只有 1 套账本 (vs Artifact 4 套) — 无 #2 STOP (Evidence 多 SSOT 不成立)。
问题在语义: EvidenceBundle 是 M3 审批包, 非 F4 目标 "支撑 Ver/Artifact 的证据"。

## 4. Audit 边界

EVIDENCE_BUNDLE_CREATED audit 事件存在 (observation); EvidenceStore 是 domain store —
audit 非 SSOT (符合)。
