# DOCUMENTATION MATRIX (STEP11.0, 2026-09-02)
> 目录级分类 (全仓 1051+ .md; docs/ 内 1005 + 根 10 + tests/benchmark 28 + 其他 8)
> 分类: A-CANONICAL / B-UPDATE / C-MERGE / D-REPLACE / E-ARCHIVE / G-TEMP
> 规则: E ≠ 删除 (历史证据保留); 过时 ≠ 无价值

| Path | Count | Category | Truth | Canonical Owner | Action |
|------|-------|----------|-------|-----------------|--------|
| docs/00-index/ | 5 | A-CANONICAL | T0-T2 | 本目录 | NEW (本 STEP) |
| docs/audit/product-system-baseline/ | 21 | A-CANONICAL | T0 | STEP10_DOMAIN_FREEZE.md | KEEP (cf81d24a 已提交) |
| docs/audit/project-reality/ | 5 | A-CANONICAL | T1 | PROJECT_PROGRESS_SNAPSHOT | KEEP (cf81d24a) |
| docs/audit/capability-maturity/ | 10 | A-CANONICAL(评估) | T4-historical | MASTER_STATUS_TABLE | KEEP (STEP7 历史评估) |
| docs/audit/fix-sprint-design/ | 13 | A-CANONICAL(设计,待批) | T5 | STEP11 status | KEEP (待人工批准) |
| docs/audit/fact-discovery/ | 49 | E-ARCHIVE(audit) | T4 | — | KEEP (STEP1-5 证据链) |
| docs/audit/git-reality/ | 2 | E-ARCHIVE(new) | T4 | — | KEEP |
| docs/architecture/ | 81 | A/B 混合 | T0/T2/T4 | orchestration-contract + data-governance = T0; 其余 T4 | KEEP; 引用以 2 份契约为准 |
| docs/audit/ (其余 ~197) | 197 | E-ARCHIVE(audit) | T4 | — | KEEP (S10 系列/phase 历史) |
| docs/sprint10/ | 329 | E-ARCHIVE | T4 | — | KEEP 原位 (历史最大块) |
| docs/sprint7-9/ | 24 | E-ARCHIVE | T4 | — | KEEP |
| docs/adr/ | 35 | E-ARCHIVE | T4 | — | KEEP (历史 ADR) |
| docs/design/ | 54 | E-ARCHIVE | T4/T5 | — | KEEP |
| docs/archive/ (含 legacy-docs/roadmap) | 49 | E-ARCHIVE | T6 | — | KEEP (已归档) |
| docs/product/ + docs/products/ | 19 | E-ARCHIVE | T4/T5 | — | KEEP |
| docs/cli/ getting-started/ community/ case-study/ validation/ release(s)/ | 40 | E-ARCHIVE/未分类 | T4/T5 | — | KEEP; 新代码引用需核对 (可能 BROKEN_REFERENCE) |
| docs/ (顶层 42) | 42 | E-ARCHIVE/未分类 | T4/T5 | — | KEEP |
| (根) README.md | 1 | B-UPDATE | T2 | 本文件 | UPDATED (本 STEP) |
| (根) AI Software Factory — 产品方案书/说明书 | 2 | E-ARCHIVE(愿景) | T5 | — | KEEP (原则源 §STEP6 27 原则) |
| (根) LLM智能路由设计说明.md | 1 | E-ARCHIVE | T5 | — | KEEP (历史设计; LLMRouter 消费 0) |
| (根) CLI命令参考文档.md | 1 | B-UPDATE(需核对) | T3 | — | KEEP; 需逐命令核对 (标记 NEEDS HUMAN) |
| (根) CHANGELOG/CODE_OF_CONDUCT/CONTRIBUTING/LICENSE/SECURITY/OPEN-CORE | 6 | KEEP | T2/T3 | — | KEEP |
| tests/benchmark/ | 28 | G-TEMP(测试数据) | T4 | — | KEEP (测试配套) |
| demo/ desktop/ examples/ .github/ | 8+ | E-ARCHIVE/未分类 | T4/T5 | — | KEEP |

## DELETE 判定: 0 份
(无明确垃圾/重复/临时 AI 输出需删 — 全部保留为历史证据)

## NEEDS HUMAN DECISION
1. docs/ 顶层 42 份未分类 (含大量中文计划/方案)
2. CLI命令参考文档.md (命令核对)
3. docs/cli/ + validation/ 等含代码引用的旧文档 (BROKEN_REFERENCE 风险)
