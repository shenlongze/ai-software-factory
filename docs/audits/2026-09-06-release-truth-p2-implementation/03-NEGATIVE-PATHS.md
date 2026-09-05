# 03 — NEGATIVE PATHS (P2-A IMPL, 2026-09-06)

## 实证 (测试 + 真实 E2E)

| 场景 | 结果 |
|---|---|
| ver-* FAIL | gate REJECTED (missing: verification_not_pass) → execute BLOCK → ≠RELEASED |
| ver PASS 但 EVD 缺失 | gate REJECTED (missing: evidence_missing) → ≠RELEASED |
| 无 ver/art (空 run) | REJECTED (missing: artifact+verification) |
| 无 governance approval | execute BLOCK (FAIL→BLOCK 语义) |
| gate 通过 + approval | RELEASED |

关键: 绝不因 EXS SUCCESS 自动 PASS / 自动 RELEASED — release 只信 canonical ver/EVD。
