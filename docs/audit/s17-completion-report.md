# S17 Workforce Governance & Human Approval — Completion Report

> 日期: 2026-08-29 | HEAD: (S17 commit) | v1.1.323

## 1. GAP Audit
Artifact Lifecycle 已有 approval gate(S1)+ audit 事件;缺 ApprovalRequest 实体 + Policy + Gate + Release + CLI/API。

## 2. Architecture
```
ApprovalRequest (persisted, append-only history)
  → decide (requester != approver, human only)
  → GovernanceGate.check (从 domain facts 投影, 非第二事实源)
  → Release Gate (verification + evaluation + approval + policy)
```

## 3. Governance Contract — REAL
approval_id/subject_type/subject_id/run_id/artifact_ids/requested_by/requested_at/decision/decided_by/decided_at/reason/policy_id/history(append-only)。

## 4. Policy — REAL
code_generation/test_execution = low(no approval);production_apply/release = high(human approval + verification)。

## 5. Permission Boundary — REAL
- Agent 不能 self-approve(requester != approver)
- Agent 不能 approve(只有 human,测试证明 qa_agent 拒绝)
- 伪造 approval_id → ValueError

## 6. Governance Gate — REAL
check(): {allowed, reason, policy_id, missing} — 必须解释为什么阻断。

## 7. Release Gate — REAL
release(): verification + evaluation + approval + 无 stale 全过才 allowed;缺任一 → BLOCKED + missing。

## 8. Approval 绑定 immutable Artifact — REAL
approval 绑定 artifact_ids + run_id;来自其他 run 的 approval → approval_stale → BLOCKED。

## 9. Audit/Evidence — REAL
APPROVAL_REQUESTED/APPROVAL_DECIDED/GOVERNANCE_ALLOWED/BLOCKED 事件(EVENT_TYPES 已有)+ payload evidence。

## 10. CLI + API — REAL(共享 Service)
```
factory governance check/status <run_id>
factory approval-request list/show/request/approve/reject
POST /api/production-runs/{id}/approval-requests
GET  /api/production-runs/{id}/governance
GET  /api/approval-requests(+/{id})
POST /api/approval-requests/{id}/approve | /reject
```
openapi 151 paths (+6)

## 11. Real Approve E2E — PASS
request → PENDING → human approve → APPROVED → release allowed + audit 事件存在。

## 12. Real Reject E2E — PASS
request → human reject → REJECTED → release BLOCKED,状态保留。

## 13. 测试 — 14 新增
policy/lifecycle/self-approve/agent-approve/fake-id/幂等/gate-blocked/stale/release-gate/reject/CLI/API/approve-E2E/reject-E2E

## 14. Regression
```
全量 llm + core: 783 passed + 5 skipped (零失败)
openapi: 151 paths
Zero-Stub: PASS
```

## 15. Commits
feat(治理): S17 Workforce Governance & Human Approval + chore(版本): bump v1.1.323 + tag

## 16. Known Limitations
- Expiration 未实现(approval 无限期有效,直到 artifact 变 stale)
- Governance read model 未缓存(每次 check 全量扫描)—— 正确性优先

## 17. Next Recommended Sprint
S18: Production Release Pipeline & Approval UI — 把 release gate 接入 production run 终态 + Web 审批界面。

## Final Verdict
> **AI 能生产,且生产行为受正式权限、验证、评价、人类批准和可审计证据约束。**

**S17 = PASS** — Agent 不能自批准、Governance Gate 必须解释阻断原因、Release 缺任一条件即 BLOCKED、Approval 绑定不可变 Artifact、全链审计可追溯。真实 Approve/Reject E2E 均通过。
