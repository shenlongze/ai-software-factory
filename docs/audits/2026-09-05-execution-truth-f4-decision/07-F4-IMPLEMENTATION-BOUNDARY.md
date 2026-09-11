# 07 — F4 IMPLEMENTATION BOUNDARY (P0-F4 DECISION, 2026-09-05)

> F4 implementation 唯一范围 — 本阶段不执行

---

## 1. F4 implementation ONLY covers

1. Canonical Artifact integration (S2 art-* 接入生产执行路径)
2. Production artifact creation boundary (create_artifact 属执行 contract)
3. Artifact lifecycle enforcement (I8 硬约束接入)
4. Artifact ↔ TaskRun/EXS relation (node_run_id 已建; exs_id 新增)
5. Canonical Evidence domain (EVD-* store + writer)
6. Verification ↔ Evidence relation (ver.evidence_ref → EVD-*)
7. Artifact ↔ Verification relation (多对多 join, 选向)
8. Idempotency (artifact create 去重 / EVD 幂等)
9. Recovery (artifact/EVD 与 run 恢复语义)
10. Real E2E (Task→run→EXS→art-*→ver-*→EVD-* 全链)
11. CLI/API contract where necessary
12. Audit observation (ART_*/EVD_* 事件)

## 2. F4 不包括

Release / Learning / Replanning / Productization / WebUI redesign /
Enterprise auth / permission system / ERP/CRM / legacy migration (exec ART →
S2 / ev-* → EVD 等)

## 3. 边界原则

- 不改 F0-F3 已提交语义 (见 05-F0-F3-IMPACT)
- 不迁移 legacy (见 06-LEGACY-BOUNDARY)
- Artifact/Evidence/Verification 各自独立 domain fact, 不合并
- EVD-* 全新, 与 ev-* 分离

## 4. F4 implementation 建议顺序 (后续单独批准)

1. S2 扩展: create_artifact + exs_id (向后兼容)
2. execute_node_run/finalize 接入: 执行产物 → create_artifact (I8)
3. gateway 委派产物收纳 (patch/文件 → art-*)
4. EVD-* Evidence domain (仿 verification_domain)
5. ver.evidence_ref 填充 + ver↔art join
6. API/CLI 投影 + E2E
