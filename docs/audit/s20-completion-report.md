# S20 Release Verification Pipeline + Approval Expiration — Completion Report

> 日期: 2026-08-29 | HEAD: (S20 commit) | v1.1.326

## 1. GAP Audit
Release apply 后直接 RELEASED(无 verification);Approval 无 expires_at。verify_pytest/syntax 现成复用。

## 2. Release Verification Pipeline — REAL
状态机升级: RELEASING→VERIFYING→RELEASED;apply 后真实 verification(python_syntax + pytest subprocess);FAIL → FAILED(不 fake)。

## 3. Verification Contract — REAL
verification_checks: check_id/type/command/exit_code/stdout/stderr/duration/evidence;持久化在 release/rollback 记录。

## 4. Rollback Verification — REAL
Rollback 状态机: ROLLING_BACK→VERIFYING→ROLLED_BACK;apply 后同样验证。

## 5. Apply ≠ Release Success — REAL
测试证明: apply 成功但 workspace 语法坏 → FAILED(不 RELEASED)。

## 6. Approval Expiration — REAL
expires_at = requested + TTL(24h);可注入 clock(set_clock)确定性测试。

## 7. Expired → BLOCKED — REAL
check_governance: now >= expires_at → missing approval_expired + approval_expired=true;取最新 APPROVED(新 approval 正常)。

## 8. Governance — REAL
approval_expired 明确 reason;跨 run 过期不复用。

## 9. Audit — REAL
RELEASE_VERIFICATION_STARTED/COMPLETED/FAILED + ROLLBACK_VERIFICATION_* 事件注册。

## 10. CLI/API — REAL
factory release verify + GET /api/releases/{id}/verification + /api/rollbacks/{id}/verification(openapi 165 paths,+2)。

## 11. Real E2E — PASS
release→apply→verify→RELEASED(checks 持久化);语法坏→FAILED;pytest 真实 subprocess PASS;rollback→verify→ROLLED_BACK;过期→BLOCKED→新 approval→allowed。

## 12. Tests — 10 新增
verified-after-apply/evidence/failure-not-released/rollback-verified/expiration-blocked/new-approval/cross-run-expired/CLI/API/pytest-E2E

## 13. Regression
```
全量 llm + core: 814 passed + 5 skipped (零失败) | Zero-Stub: PASS
```

## 14. Commits
feat(生产核心): S20 Release Verification & Approval Expiration + chore(版本): bump v1.1.326 + tag

## 15. Known Limitations
- verification 只跑 syntax + workspace 内 pytest(无独立 test 集注入)
- 无 verification retry(FAIL 即终态)

## 16. Remaining Production Gaps
1. 完整 workspace diff 恢复(S19 遗留)
2. Release rollback 自动化触发

## 17. Next Recommended Sprint
S21: Release Health Monitor — release/rollback 后持续验证 + 失败自动 rollback。

## Final Verdict
> **Apply ≠ Verify;Release/Rollback 必须经过真实 Verification Pipeline;Approval 有明确有效期,过期即 BLOCKED。**

**S20 = PASS** — Release 状态机含 VERIFYING(apply 后真实 syntax+pytest subprocess 验证,FAIL 不 RELEASED)、Rollback 同样验证、Approval expires_at + 可注入 clock + 过期 BLOCKED(approval_expired 明确 reason)、新 approval 正常、审计完整、CLI/API 共享 Service、全量回归 0 失败。
