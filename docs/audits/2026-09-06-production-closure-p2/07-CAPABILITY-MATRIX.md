# 07 — CAPABILITY MATRIX (P2 GAP AUDIT, 2026-09-06)

| Capability | Reality | SSOT | Writer | Input | Output | Traceability | E2E | Level | Gap | Priority |
|---|---|---|---|---|---|---|---|---|---|---|
| C-030 Release | rel-* M3 域 | releases.json (M3) | release_service | M3 run | apply+RELEASED | M3 only | 测试 M3 mock | M1 | 不连 P0/P1 | HIGH |
| C-031 Production Closure | P0 全链 | art/ver/EVD stores | node_runtime/finalize | EXS | EVD | REAL | 4/4 | M4 | 止于 EVD | — |
| C-032 Experience Bridge | exp 84 | memory exp store | AutoLearner/extraction | EXS | exp-* | source FK | 真实 84 | M3 | — | — |
| C-033 Learning | 引擎全 | intelligence/ + learning_trace | learning_engine_v2 | exp? | candidate/profile | trace | 0 数据 | M2 | 无真实输入 | HIGH |
| C-034 Learning Consumption | 路由消费代码 | agent_profiles.json | refresh_agent_profiles | exp | 路由排序 | — | 0 数据 | M1 | profile 0 | HIGH |
| C-035 Feedback Loop | 代码通 | 同 C-034 | — | — | — | — | 无 | M1 | 未真实闭环 | HIGH |
| C-036 Continuous Improvement | — | — | — | — | — | — | — | M0 | 依赖 C-033~35 | LATER |
