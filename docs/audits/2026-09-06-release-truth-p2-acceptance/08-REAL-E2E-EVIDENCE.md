# 08 — REAL E2E EVIDENCE (P2-A ACCEPTANCE, 2026-09-06)

fresh 复跑 4/4 (真实 service, 隔离 tmp):

| Case | 结果 |
|---|---|
| E2E-1 positive | IDEA→…→PLAN→TASK→run→EXS→art→ver PASS→EVD→RELEASE RELEASED; reverse 全 FK 到 IDEA |
| E2E-2 negative | ver FAIL → REJECTED (≠RELEASED) |
| E2E-3 negative | missing EVD → REJECTED (≠RELEASED) |
| E2E-4 idempotency | 同 run 幂等单 release; 无 approval BLOCK |

store 实证 (F8): E2E 后 release_truth.json 含 4 RELEASE-* 记录 —
RELEASED (ver 1+evd 1) / REJECTED ×2 / … 真实写 canonical SSOT。
