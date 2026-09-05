# 06 — LEGACY BOUNDARY (P0-F4 ACCEPTANCE, 2026-09-05)

> legacy 隔离验收 — 无 retroactive fabrication / 无跨域污染

---

## 1. 全局搜索确认 (F4 新链未连接 legacy)

| legacy | 状态 |
|---|---|
| exec ART-* (225) | 未迁移/未重包装为 art-*; F4 收纳只写新 art-* |
| org ArtifactRegistry (24) | org 域独立, 未触碰 |
| EXS patch files (75) | 外置文件保留; 未转 art-* (文件名非 FK) |
| ev-* EvidenceBundle (9) | M3 approval package 保留; 未升级 EVD/未转换/未重连 ver-* |
| EXR-* / TASK-GW-* / task-e1-* / T-* / task-chg-* / 历史 session_exec | F0-F3 边界保持 |

## 2. 无 retroactive fabrication

- 历史数据不生成 art-*/EVD-* (create 仅新执行路径触发 — node_runtime/rollback)
- 无 FK backfill (不按 filename/audit/时间猜关系; 代码零命中)
- legacy 无法进入新链 = 预期 (D1/D2), 非缺陷

## 3. 隔离证据

- evidence_domain 只读 <root>/evidence/EVD-*.json, 不读 projects/*/evidence/ev-*
- artifact_lifecycle 只写 S2 art-* store, 不读 exec/artifacts.json / org
- 测试: test_legacy_evd_prefix_disjoint / test_verify_evidence_ref_kept_f3

## 4. 结论

**Legacy isolation PASS** — 无迁移/无重建/无跨域污染。
