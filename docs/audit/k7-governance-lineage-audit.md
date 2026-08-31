# K7 Governance & Lineage Audit

> 日期: 2026-08-29

## 审计完整性
一次完整操作可回溯: conv message → intent → req → decision → project → sprint → task → run → evidence
- 谁决定: decision_ 实体 (created_by)
- 为什么执行: req parent=conv, task parent=project
- 谁执行: run (executor)
- 使用什么 Agent: task role
- 如何验证: run state + verification
- 是否 Approval: task_approval_status
- 最终结果: evidence state

## Governance
- Approval 不可绕过 (J7: PENDING → 不执行; APPROVED → 执行)
- View ≠ Execute (Control Tower 只读)
- 操作全 Audit (S43 event)
