# 00 — F4 DECISION OVERVIEW (2026-09-05, READ-ONLY / CONTRACT FREEZE)

> 阶段: P0-F4 Architecture Decision Freeze — 只冻结决策, 零 implementation
> 前置: F4 GAP AUDIT (NO-GO) → 本阶段把 D1-D4 冻结为正式 Contract
> 基线: 794e24d7 (F3 committed) | F4 audit: docs/audits/2026-09-05-execution-truth-f4/
> 产出: 本目录 9+1 份决策文档; 零代码/零数据/零 git 改动

---

## 1. 决策汇总

| 决策 | 冻结内容 | 状态 |
|---|---|---|
| D1 | Canonical Artifact = S2 art-*; exec ART-*/org registry/EXS patches = LEGACY | APPROVED |
| D2 | 现有 ev-* EvidenceBundle = LEGACY approval package; 未来 Evidence = 新独立域 (EVD-*) | APPROVED |
| D3 | 多对多 FK 契约: TaskRun→Artifact[], Verification[]; Verification↔Artifact[]; Verification→Evidence[] | APPROVED |
| D4 | I8 = Production Core 硬约束; Artifact creation 属正式 production contract | APPROVED |

**F4 IMPLEMENTATION = NO-GO** (本阶段不实现; 待批准后单独 implementation phase)

## 2. 上层契约 (不得重定义)

Task=TASK-* / TaskRun=run-* / EXS=EXS-* / Verification=ver-* (F3 SSOT);
Task.exec_ref→EXS; NodeRun.verification=内部快照非 SSOT; Audit=observation;
legacy (EXR/TASK-GW/task-e1-*/历史 M3/session_exec) 隔离。

## 3. 关键原则

Snapshot ≠ Domain Fact | Artifact ≠ Verification ≠ Evidence ≠ Approval ≠ Audit |
Audit ≠ SSOT | WebUI ≠ Business Truth | Legacy History ≠ Current Production Truth
