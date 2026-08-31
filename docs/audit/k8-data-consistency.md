# K8 Data Consistency — Core/API/UI 三层矩阵

> 日期: 2026-08-29 | 纯审计

| Entity | Core SSOT | API | UI | Realtime | Status |
|--------|-----------|-----|----|----------|--------|
| Conversation | unified_contract (conv_) | /api/conversations | ConversationPage | polling | ✅ 一致 |
| Project | unified_contract (project_) | /api/projects-os | WorkPage/Tower | polling | ✅ 一致 |
| Sprint | unified_contract (sprint_) | projects-os/status | WorkPage | polling | ✅ 一致 |
| Task | unified_contract (task_) | task-trees + tasks | WorkPage/Tower | polling | ✅ 一致 |
| Agent | workforce (S30) | /api/workforces | Tower who-working | polling | ⚠️ 旧/新并存 |
| Execution | production_run (S3) | /api/production-runs | Tower drill | polling | ✅ 一致 |
| Evidence | unified_contract (evidence_) | projects-os + ops | Tower drill | polling | ✅ 一致 |
| Approval | governance (S17) | /api/approvals (旧) + tasks/approval (新) | WorkPage | polling | ⚠️ 双 API |
| Incident | self_healing (S39) | /api/incidents | 无 UI 视图 | - | ⚠️ 无视图 |

## GAP
- Agent 状态: 旧 /api/workforces vs 新 operational_state.who_is_working — 双来源 (建议收敛到 ops)
- Approval: 旧 /api/approvals vs 新 tasks/{id}/approval — 双 API (建议收敛)
- Incident: 后端 REAL, UI 无视图 (P3)
