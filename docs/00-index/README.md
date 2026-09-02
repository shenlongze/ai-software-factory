# AI Factory — Documentation Index (STEP11.0, 2026-09-02)

> Canonical Documentation System 入口。本目录 = 当前系统事实的单一导航。
> 本目录文档 = TRUTH_LEVEL T0-T2。历史审计/设计 = 见 DOCUMENTATION_MATRIX (归档/审计, 非当前真相)。

## READ FIRST (任何 AI/人进入项目)

```
README.md (根)                       — 项目身份 + 本索引链接
docs/00-index/README.md              — 你在这里
docs/00-index/CURRENT_SYSTEM_TRUTH.md — 当前系统事实 (产品/架构/Domain/SSOT/状态) ← 最重要
docs/00-index/DOCUMENTATION_MATRIX.md — 全库文档分类 (1051+ 份, 目录级)
docs/00-index/DOCUMENTATION_GOVERNANCE.md — 文档规则 (Canonical Owner/Truth Level)
docs/00-index/DOCUMENTATION_DEPENDENCY_MAP.md — 文档引用关系
```

## Canonical Contract (最高 Truth, T0)

```
docs/audit/product-system-baseline/   — STEP9-10 冻结产物
  STEP10_DOMAIN_FREEZE.md             — 主冻结文档 (20 节, 人工批准 2026-09-02)
  01~10_*.md                          — 10 份分域 Contract (ADR/Domain/SSOT/Relation/
                                          Execution Truth/Req-PRD/Agent/Model/Module)
docs/architecture/orchestration-contract.md       — 会话编排宪法 (含 §24 Plan Closure)
docs/architecture/orchestration-recovery-contract.md — 崩溃恢复契约
docs/architecture/data-governance.md              — 数据治理宪法 (8 条)
```

## Current Reality (T1, 只读事实快照, 权威 = 代码+运行时)

```
docs/audit/project-reality/PROJECT_PROGRESS_SNAPSHOT.md — 1 页状态
docs/audit/project-reality/MASTER_STATUS_TABLE.md       — 29 能力基准
docs/audit/capability-maturity/                        — STEP7 成熟度 (85.2/75.0/49.8 历史评估)
docs/audit/fix-sprint-design/                          — STEP11 Fix 设计 (待人工批准)
```

## 重要区分

| 目录 | 性质 |
|------|------|
| docs/00-index/ | CANONICAL (当前真相导航) |
| docs/audit/product-system-baseline/ | CANONICAL CONTRACT (T0, 人工批准) |
| docs/architecture/ | 混合: 部分 T0/T2 (以 orchestration/data-governance 为准) |
| docs/audit/ (其余) | HISTORICAL EVIDENCE (T4, STEP1-11 + S10 系列 + phase*) |
| docs/sprint10/ + sprint7-9/ + adr/ + design/ | HISTORICAL (T4/T5) |
| docs/archive/ | 已归档历史 (T6) |
| 根目录 10 份 | 见 MATRIX (产品方案书=T5 愿景源, README 已更新) |
