# 06 — LEGACY BOUNDARY (P0-F4 DECISION, 2026-09-05)

> 正式冻结 legacy 清单 — 不迁移/不转换/不补 FK/不 retroactive

---

## 1. Artifact legacy (冻结)

| 对象 | 定义 | 处置 |
|---|---|---|
| exec ART-* (225) | LEGACY / ADAPTER (AgentRuntime 快照) | 保持只读; 新执行不再产生新 ART-* (D4) |
| org ArtifactRegistry (24) | HISTORICAL PROJECTION (M3/S14 项目域) | 保持 org 域; 不与 canonical 连 |
| EXS patch files (75) | LEGACY 外置产物 | 保留文件; 文件名非 FK |

## 2. Evidence legacy (冻结)

| 对象 | 定义 | 处置 |
|---|---|---|
| ev-* EvidenceBundle (9) | LEGACY / APPROVAL PACKAGE (M3) | 保持; 不改语义/不重连 ver-*/art-*/EXS-*/run-* |

## 3. 禁止 (全部 legacy 通用)

- 自动迁移 / 自动转换 / 自动补 FK
- retroactive reconstruction
- 按文件名猜 identity / 按 audit 猜关系 / 按时间猜关系
- 为"闭环好看"伪造历史 art-*/EVD-* 或 FK

## 4. Migration phase (独立, 未启动)

历史数据若未来需迁移 (如 exec ART → S2 art-*), 必须另立 migration phase —
不在 F4 implementation 范围, 本阶段亦不做。
