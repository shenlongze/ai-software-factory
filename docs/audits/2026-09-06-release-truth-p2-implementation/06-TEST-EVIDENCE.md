# 06 — TEST EVIDENCE (P2-A IMPL, 2026-09-06)

## P2-A 测试 14/14 (test_p2_release_truth.py)

identity/store / auto-collect P0 facts / single-writer / gate PASS /
gate FAIL verification / gate FAIL missing evidence / execute 无 approval BLOCK /
execute + approval RELEASED / supersede / revoke / idempotent per run /
idempotency key / trace chain / no ver-art reject / rel-* 隔离

## 回归

- P1 15 + F1-F4 55 + P2-A 14 = 84 新增域全 PASS
- M3 release/governance/rollback/integrity/ops + node 相关: 161 passed, 0 failed
  (governance 白名单加 release 零破坏)

## 真实 E2E 4/4 (fresh 2026-09-06)

E2E-1: P1 全链 + P0 exec + RELEASE RELEASED + reverse trace 到 IDEA
E2E-2: ver FAIL → REJECTED ≠RELEASED
E2E-3: missing EVD → REJECTED ≠RELEASED
E2E-4: idempotent create + 无 approval BLOCK
