# 00 — P1 CONTRACT FREEZE (2026-09-05, READ ONLY)

> 阶段: P1 Product Truth Contract Freeze — 只冻结架构契约, 不实施
> 前置: P1 GAP AUDIT (NO-GO) → 本阶段 D1-D20 决策冻结
> 基线: P0 committed (d849a108 / 794e24d7 / 69ca3367)
> 产出: 本目录 15 份契约文档; 零代码/零数据/零 git 改动

---

## 1. 核心原则

> Domain Truth ≠ Document ≠ UI State ≠ Event ≠ Cache ≠ Snapshot

P0 教训: 无唯一事实源 = 无真正 Truth。P1 必须预先冻结 Product Truth,
避免 Requirement/PRD/Plan 变成第二个"多账本"。

## 2. P1 Product Truth Chain (冻结目标)

```
User Intent (输入事实, 非 entity)
   ↓
IDEA-*
   ↓
DISC-*
   ↓
REQ-*
   ↓
PRD-*
   ↓
PLAN-*
   ↓
TASK-*  ←── P1→P0 唯一边界
   ↓
═══ P0 EXECUTION TRUTH (冻结, 不重定义) ═══
run-* → EXS-* → art-* → ver-* → EVD-*
```

## 3. 总判定

**Status: GO (contract 级)** — 六层 Domain Entity 可冻结、无 P0 conflict、
无 STOP condition 触发; 等待人工批准后进入 P1 Implementation。

详见 14-GO-NO-GO.md。
