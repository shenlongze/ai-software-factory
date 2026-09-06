# 16 — REAL E2E DESIGN (P2-C CONTRACT, 2026-09-06)

> 只设计, 不执行 (Implementation 期验收门)

## E2E-C1 全链 (Production→Release→Experience)
IDEA→…→TASK→run→EXS→art→ver PASS→EVD→RELEASE RELEASED→exp
验证: exp.task_run_id / exp.exs_id / exp.release_id (release 决策经验) +
reverse: exp → run → task → plan → prd → req → disc → idea

## E2E-C2 失败恢复
run-1 EXS FAIL → exp(FAIL); recovery run-2 EXS SUCCESS → exp(SUCCESS);
两条独立, 旧不覆盖

## E2E-C3 验证失败修复
ver FAIL → 修复 → ver PASS → 1 条 exp (终态 PASS 为准)

## E2E-C4 Release 拒绝
ver FAIL → RELEASE REJECTED → release 决策 exp (FAILURE_PATTERN, release_id)

## E2E-C5 幂等
同 EXS finalize ×2 → 1 exp

## E2E-C6 Release 幂等
同 RELEASE bridge ×2 → 1 release exp
