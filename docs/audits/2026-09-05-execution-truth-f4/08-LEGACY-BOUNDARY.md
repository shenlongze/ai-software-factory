# 08 — LEGACY BOUNDARY (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> Legacy 连接检查 — 无错误重连

---

## 1. 各账本 legacy 归属

| 对象 | 归属 | 证据 |
|---|---|---|
| EXR-* / TASK-GW-* / task-e1-* / T-* / task-chg-* | LEGACY (F0-F3 已定) | 未触碰 |
| exec ART-* (task_id=T001-5/task-e1-*) | exec 域 + M3 legacy 混合 | task_id 前缀 |
| org registry (P-* project) | M3/S14 项目域 | P-{id}-R{ms}-TYPE |
| ev-* (ai-factory slug) | M3 EvidenceBundle | task_id=旧 slug |
| S2 art-* | Production Core (S1/S2) — 唯一契约域 | artifact_lifecycle |
| ver-* (F3) | canonical (F3 冻结) | verification_domain |

## 2. 错误重连扫描 (应零)

- 无代码把 task-e1-*/T001/EXR 映射到 art-*/ART-*/ver-* canonical
- 无迁移脚本 (exec ART → S2 / org → S2 / ev-* → 新 Evidence)
- ev-* artifacts 字段空 — 未指向任何 canonical artifact
- exec ART event_refs 指 audit event id (数字 1605…) — 非 canonical

## 3. 结论

Legacy 隔离本身 OK (无主动重连); 问题是 **真实产物 (exec/org/patches/ev-*) 天然
游离在 canonical 链外**, 未连接 ≠ 被错误连接。F4 若要闭环需正向决策如何收纳,
而非"清理历史"。
