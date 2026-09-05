# 08 — LEGACY BOUNDARY (P0-F4 IMPL, 2026-09-05)

> F4 后 legacy 隔离确认

---

## 1. 隔离状态 (未迁移/未重建)

| 对象 | 状态 |
|---|---|
| exec ART-* (225) | LEGACY 保留; 未迁移未重包装; F4 收纳只写新 art-* |
| org ArtifactRegistry (24) | LEGACY (org 域) 未触碰 |
| EXS patch files (75) | LEGACY 外置文件保留; 未转 art-* |
| ev-* EvidenceBundle (9) | LEGACY M3 approval package; 未升级/未重连 |
| EXR/TASK-GW/task-e1-*/T-*/task-chg-*/历史 session_exec | F0-F3 边界保持 |

## 2. 无伪造/无 retroactive

- 历史数据不生成 art-*/EVD-* (create 仅新执行路径触发)
- 无 FK backfill (不按 filename/audit/时间猜关系)
- legacy 无法进入新链 = 预期 (D1/D2/F4 §21)

## 3. 证据 (测试)

test_legacy_evd_prefix_disjoint: M3 ev-* 在 projects/{slug}/evidence/ 下,
EVD-* 在 <root>/evidence/ 下 — 前缀 + 路径双层隔离, evidence_domain 不读 legacy。

## 4. 未来迁移 (另立 phase, 未启动)

exec ART-* → S2 / ev-* → EVD 迁移若需, 单独 migration phase — F4 不包含。
