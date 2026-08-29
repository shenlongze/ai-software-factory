# S17 Architecture Proposal — Workforce Governance & Human Approval

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Governance Contract (冻结)
```
ApprovalRequest:
  approval_id / subject_type (production_run/artifact) / subject_id /
  production_run_id / artifact_ids / requested_by / requested_at /
  decision (PENDING/APPROVED/REJECTED) / decided_by / decided_at / reason /
  evidence_ids / policy_id / history (append-only)

GovernancePolicy:
  action / risk_level (low/medium/high) / approval_required /
  allowed_approvers (human/role) / required_evidence / required_verification

GovernanceGate.check(run_id):
  → {allowed, reason, policy_id, missing: [...]}
```

## 2. Policy (最小真实)
```
code_generation:     low  → no approval
test_execution:      low  → no approval
production_apply:    high → human approval required
release:             high → human approval required (+verification+evaluation)
```

## 3. Release Gate
```
release_allowed = verification PASS AND evaluation PASS AND approval APPROVED AND policy PASS
缺任一 → BLOCKED (reason + missing 明确)
```

## 4. 安全
- requester != approver (Agent 不能 self-approve)
- Approval 绑定 immutable artifact_ids + production_run_id (staleness: 新 Artifact 需新 Approval)
- Governance 只读 Artifact, 不写 Workspace (Lifecycle 负责 Apply)
- 无 boolean approval, 无第二事实源 (读 domain facts)

## 5. CLI/API
```
factory governance check/status <run_id>
factory approval list/show/request/approve/reject
POST /api/production-runs/{id}/approval-requests
GET  /api/production-runs/{id}/governance
GET  /api/approval-requests(+/{id})
POST /api/approval-requests/{id}/approve | /reject
```

## 6. Workforce 集成
Governance 是横切控制层 (Workforce→Production→Artifact 之上), 不是 Mega-Agent。
