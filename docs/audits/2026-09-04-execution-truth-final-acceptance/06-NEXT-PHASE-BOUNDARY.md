# 06 — NEXT-PHASE BOUNDARY (P0-FINAL, 2026-09-04)

> F3/F4 与产品链边界 — 明确已完成/未完成, 不混入 F2

---

## 1. DONE (本验收范围)

- F0 Contract Freeze (2026-09-04-execution-truth-contract/)
- F1 Identity Closure (2026-09-04-execution-truth-f1/)
- F2 Completion Writeback (2026-09-04-execution-truth-f2/)

## 2. NOT DONE — 后续阶段 (不混入)

| 阶段 | 内容 | F3/F4 前置 |
|---|---|---|
| F3 | Verification SSOT: ver-* identity, verification policy, pytest convergence; 归属 TaskRun (F0 已冻结) | finalize 已预留 verification metadata 字段; O-1 (EXS.result vs verify 统一) 应在此解决 |
| F4 | Artifact/Evidence Traceability: exec ART-* → S1 art-* 投影; Evidence ev-* 挂 TaskRun; T-9 全链 | 依赖 F3 |
| Release | v0.1.0 发布门 + wheel | 独立 |
| Learning | Experience 消费端 (85 条 0 消费) | 独立 |
| Replanning | 失败自动重规划 | F2 明确不做 |
| 产品链 | Requirement→PRD→Plan 全链 (PRD 实体缺失) | 独立 (FX-03/INV-011) |
| Model Policy | LLMRouter production 消费 | 独立 (FX-05) |
| Agent ecosystem / Productization | 洋葱式开源 / 增长 | 战略层 |

## 3. F3 边界 (即将)

- 不做: 本验收后停止; 不实现 F3
- F3 验收依赖: F0 (Verification 归属 TaskRun 已冻结) + F1 (run-* 身份稳定) + F2
  (finalize 已落 verification metadata) — 身份链已就绪

## 4. 遗留决策项 (非 F3 阻塞)

- 历史 6 个 E2E session_exec 处置 (标记 abandoned / 清理) — 用户决策
- workflow_runner (S14) T-*/R{ms} 域边界正式化 — O-2
- EXS.result 判定语义统一 — O-1 (F3)
