# 09 — F4 DECISION (P0-F4 DECISION FREEZE, 2026-09-05)

> 最终决策 — 冻结

---

## 1. 决策结果

```
D1 (Artifact canonical) = APPROVED
    Canonical Artifact = S2 art-* domain (唯一 lifecycle + I1-I12 + writer + store)
    exec ART-* / org ArtifactRegistry / EXS patch files = LEGACY / ADAPTER /
    HISTORICAL PROJECTION (不升级, 不迁移, 不伪造)

D2 (Evidence semantic)  = APPROVED
    现有 ev-* EvidenceBundle (M3 approval package, 9 条) = LEGACY / APPROVAL PACKAGE
    未来 canonical Evidence = 独立 EVD-* domain (支撑 Verification 可信度的事实)
    EVD-* 与 ev-* 前缀分离, 无语义冲突

D3 (FK relationship)    = APPROVED
    多对多契约 (非 1:1 链):
    Task → TaskRun → EXS
    TaskRun → Artifact[] / Verification[]
    Verification ↔ Artifact[] (多对多)
    Verification → Evidence[] (EVD-*)
    Evidence 可被多 Verification 共享 (不可变)

D4 (I8 enforcement)     = APPROVED
    I8 = Production Core 硬约束
    Production artifact MUST NOT bypass S2 lifecycle
    Artifact creation 属正式 production execution contract (非事后补 record)
```

## 2. 唯一性声明

- Artifact: 唯一 canonical = art-*; 唯一 writer = artifact_lifecycle;
  唯一 store = S2 前缀分片
- Evidence: 唯一未来 canonical = EVD-*; ev-* = legacy (单 legacy, 非 SSOT)
- Verification: 唯一 = ver-* (F3, 不变)
- 无第 5 套 Artifact store / 无第 2 套 Evidence SSOT 创建

## 3. F0-F3 影响

**零冲突** (05-F0-F3-IMPACT 逐项核对)。
新增均为向后兼容扩展: art.exs_id 可选参数 / FK join / EVD-* 新域。

## 4. GO Gate

18/18 ✓ (08-F4-GO-GATE) — contract 级 GO 前提满足。

## 5. 最终判定

```
F4 IMPLEMENTATION = GO   (contract 级; 待用户批准启动 implementation phase)
```

**本阶段未实现任何 F4 代码; 未迁移/改写真实数据; 未 commit; 未 push。**

## 6. 回答核心问题

> 是否已拥有足够严格、唯一、不可分叉的 Artifact + Evidence Contract,
> 可以安全进入 F4 implementation?

**YES** — D1-D4 冻结后: Artifact canonical 唯一 (art-*), Evidence 语义唯一
(EVD-* vs legacy ev-*), FK 方向唯一 (多对多契约), I8 硬约束边界唯一;
F0-F3 零冲突; 无历史迁移/伪造要求; writer/owner 全部唯一。
Contract 已不可分叉, 可以安全进入 F4 implementation (待单独批准)。
