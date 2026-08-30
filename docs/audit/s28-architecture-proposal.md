# S28 Architecture Proposal — Production Quality Recovery & Verification Closure

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Recovery Attempt Contract (冻结)
```
recovery_attempt_id / production_run_id / failure_classification / source_verification_id /
repair_id / attempt_number / status(REQUESTED→RUNNING→VERIFICATION_PENDING→RECOVERED|FAILED|EXHAUSTED|BLOCKED) /
started_at / completed_at / evidence_refs
```

## 2. Recovery Policy (冻结)
```
可 repair: VERIFICATION_FAILURE (bounded max_attempts=3)
不可自动: AGENT_FAILURE / GOVERNANCE_BLOCKED / UNKNOWN → 直接 FAILED/BLOCKED (不猜测)
禁止: while failure: repair() — bounded + idempotent + flock 并发安全
```

## 3. Verification Closure (冻结)
```
RECOVERED 仅当: repair → re-production → new artifact → new verification (新 id) → PASS
禁复用旧 verification; 历史 append-only (attempt-1 FAIL 保留)
```

## 4. Repair Integration (冻结)
```
repair_fn 输入: failed_artifact + verification evidence + ctx (真实, 非"请修复代码")
复用 build_developer_repair_fn (codex) — 只走 Production Kernel, 不改 Production Truth
```

## 5. Outcome (冻结)
```
RECOVERED / FAILED / EXHAUSTED / BLOCKED
Repair 执行成功 ≠ RECOVERED (必须 verification PASS)
```

## 6. Evaluation/Optimization 集成
```
Recovery 后新 outcome → 新 evaluation; 只有 COMPLETED+PASS+valid-evaluation 才可成为 S27 ELIGIBLE
```

## 7. CLI/API
```
factory recovery inspect <id> | attempts <run> | retry <run> | status <run> | evidence <attempt>
GET /api/recovery/{id} | /api/production-runs/{id}/recovery | /api/recovery/{id}/attempts |
POST /api/recovery/{id}/retry | GET /api/recovery/{id}/evidence
```
