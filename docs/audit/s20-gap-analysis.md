# S20 Gap Analysis — Release Verification Pipeline + Approval Expiration

> 日期: 2026-08-29 | HEAD: 8d8a07a3 (v1.1.325)

## Existing REAL (复用)
| 能力 | 位置 |
|------|------|
| verify_pytest / verify_python_syntax (真实 subprocess) | verification.py (S5) |
| Release State Machine + apply | release_service.py (S18) |
| Rollback apply + workspace 恢复 | rollback_service.py (S19) |
| Approval (human only) | governance_service.py (S17) |
| Governance Gate | governance_service.py (S17) |

## Missing (S20 新增)
| GAP | 最小实现 |
|-----|---------|
| Release 状态机缺 VERIFYING (RELEASING→VERIFYING→RELEASED) | release_service.py |
| Release apply 后真实 verification (pytest/syntax) | release_service.execute |
| Rollback 后真实 verification | rollback_service.execute |
| Approval expires_at + clock provider | governance_service.py |
| Expired approval → BLOCKED (approval_expired reason) | governance_service.check |
| RELEASE_VERIFICATION_* / ROLLBACK_VERIFICATION_* / APPROVAL_EXPIRED 事件 | audit_event.py |
| CLI/API/UI 显示 verification + expiration | cli + adapter + ProductionPage |

## 设计
```
Release: ...→RELEASING→VERIFYING→RELEASED (verification FAIL → FAILED)
Rollback: ...→ROLLING_BACK→VERIFYING→ROLLED_BACK
Approval: expires_at = requested_at + policy TTL; now >= expires_at → expired → BLOCKED
clock 可注入 (测试用 fake clock)
```

## 禁止
- apply 成功直接 RELEASED / LLM 自评 / sleep 测 expiration / 第二套 executor
