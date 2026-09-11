# 11 — FALSE CLOSURE AUDIT (CLOSURE AUDIT, 2026-09-06)

| # | 问题 | 判定 | Evidence | 严重度 |
|---|---|---|---|---|
| F1 | LearningEngine 存在≠Learning works | YES (风险) | obs/cand=0 | HIGH |
| F2 | Experience 存在≠Learning 消费 | YES | engine 0 输入 | HIGH |
| F3 | Candidate schema≠生成 | YES | candidates 0 | HIGH |
| F4 | PromotionService 存在≠发生 | YES | promotions 0 | HIGH |
| F5 | AgentProfile schema≠persisted | YES | profiles 0 | HIGH |
| F6 | Router 可读≠runtime 读 | NO | persona_score 真 runtime (但无数据) | MED |
| F7 | Profile 变≠路由变 | N/A | 无 profile | — |
| F8 | 路由变≠产出改善 | N/A | — | — |
| F9 | Release 存在≠learning 消费 | YES | release→exp=0 | MED |
| F10 | 测试过≠生产闭环 | YES | E2E 在 tmp | HIGH |
| F11 | 历史执行≠当前 canonical | 注意 | exp 55 来自历史 EXS | MED |
| F12 | 多 ledger 重现 | NO | 无 (09) | — |
| F13 | WebUI 独立业务状态 | NO | (10) | — |
| F14 | CLI 绕过 writer | NO | (10) | — |
| F15 | Event 当 SSOT | NO | audit 观察 | — |
| F16 | Git tag 当 Release | NO | metadata only | — |

**学习域 F1-F5 假闭环风险 = 真实** (代码有, 数据 0)。
