# 00 — OVERVIEW (P2-A RELEASE TRUTH CONTRACT FREEZE, 2026-09-06)

> 阶段: P2-A Release Truth — Release 接入 P0 Canonical 的契约冻结 (READ-ONLY)
> 基线: 04299e26 (P1) | 前置: P2 GAP AUDIT (Release=M1, 断 P0/P1)

---

## 1. 判定摘要

- **Option B 选定**: RELEASE-{hex8} 新 canonical ID; 现有 rel-* = LEGACY (M3)
- Release Domain: entity + store + 唯一 writer + lifecycle + gate + FK + trace
- Gate 消费 canonical ver-* / EVD-* (解决 P2 G-3/G-5)
- Legacy: rel-* / M3 production_run 零迁移零回填
- P0/P1 contract 零改动 (Release 只 consume)
- **Status: GO (contract 级 — 待人工批准进入 P2-A Implementation)**

## 2. 核心契约图

```
TASK-* ──run──► run-* ──EXS──► EXS-*
  │              │              │
  │              ▼              ▼
  │           art-*          (产物)
  │              │
  ▼              ▼
PLAN-*──► TASK-*──► art-* ──ver-*──► EVD-*
                              │          │
                              └────┬─────┘
                                   ▼
                          RELEASE-*  (新 canonical)
                                   │
                                   ▼
                        (future Deployment / Learning)
```

Release **consume** P0 facts (art/ver/EVD/EXS/run/task), 不 reverse-write。
