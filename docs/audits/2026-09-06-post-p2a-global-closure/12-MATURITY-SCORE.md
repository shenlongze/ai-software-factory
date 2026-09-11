# 12 — MATURITY SCORE (CLOSURE AUDIT, 2026-09-06)

| 项 | M | Evidence |
|---|---|---|
| Product Truth | M4 | P1 committed, E2E 真 |
| Production Truth | M4 | P0 committed, E2E 真 |
| Release Truth | M4 | P2-A committed, E2E 真 + store 实证 |
| Experience Truth | M3 | 84 真 (55 EXS) 但无结构化 FK |
| Learning Truth | M1 | 引擎代码全, 0 输入数据 |
| Learning Consumption | M1 | 消费代码真, profile 0 |
| Closed Loop | M0-M1 | 无跨环数据流证据 |
| Traceability | M4 (Product/Prod/Release) / M1 (→Learning) | FK 链止于 RELEASE |
| Governance | M3 | approval 真实 (release) |
| WebUI Reality | M3 (projection) | 无业务直写 |
| CLI/API Reality | M3 | canonical 读 |
| SSOT Integrity | M4 (P0/P1/P2-A 域) | 无第二 SSOT |
