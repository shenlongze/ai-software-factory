# S17 Gap Analysis — Workforce Governance & Human Approval

> 日期: 2026-08-29 | HEAD: e526194c (v1.1.322)

## Existing REAL (复用)
| 能力 | 位置 |
|------|------|
| Artifact Approval Gate (APPLIED/COMMITTED/RELEASED 必须 APPROVED + approval_id 绑定) | artifact_lifecycle.py:239-245 |
| Artifact 不可变 (S1) | artifact_lifecycle.py |
| Audit events (APPROVAL_REQUESTED/DECIDED, GOVERNANCE_CHECK) | audit/audit_event.py |
| Evaluation (S13) / Permission Matrix (S16) | production_evaluation / workforce |

## Missing (S17 新增)
| GAP | 最小实现 |
|-----|---------|
| ApprovalRequest 持久化实体 (PENDING/APPROVED/REJECTED 状态机 + append-only history) | governance_service.py |
| Governance Policy (risk_level/approval_required/allowed_approvers) | governance_service.py |
| Governance Gate (check: allowed/missing/reason) | governance_service.py |
| Release Gate (release 必须 approval) | governance_service.py: release() |
| Agent 不能 self-approve (requester != approver) | governance_service.py |
| Approval 绑定 immutable Artifact (staleness) | governance_service.py |
| CLI/API (approval request/approve/reject, governance check/status) | cli_factory + fastapi_adapter |

## 设计
```
ApprovalRequest (persisted, append-only)
  → decide(approve/reject) [requester != approver]
  → Artifact Lifecycle gate 消费 (approval_id 绑定)
  → Release Gate (approval + verification + evaluation + policy)
```

## 禁止
- boolean approval / Agent self-approve / Governance 直接写 Workspace / 第二套事实源
