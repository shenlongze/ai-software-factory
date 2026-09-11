# 01 — Domain Map
概念 → canonical model/store/service/API (代码取证)
- Project: org Project (projects.json) | service.ProjectStore | /api/projects
- Session: console_sessions.json | SessionsStore | /api/sessions
- Conversation msg: console_sessions messages(meta.tool_calls 含 output)
- Task: ManagementStore backlog (workspace/projects/{slug}/management) |
  service.list_backlog/create_task | /api/projects/{id}/backlog
- Node/NodeRun: node_runtime.py nodes/definitions+runs | node_id=task-execution
- Workflow run: production_run.py (S46 8 阶段; stages/evidence)
- Product Truth: product_truth/*.json (ideas/discoveries/requirements/prds/plans)
- Acceptance/Release: acceptance_truth/release_truth (ACC-*/RELEASE-*)
- Artifact/Evidence/Verify: artifact_lifecycle(art-*) verifications(ver-*)
- Agent/Workforce: workforce_os/roles (capability 标签)
- Capability/Tool/Skill: capability_router(匹配) + agent_loop 内联 tool +
  skill_search(4) — 无统一注册 (偏离1)
- Memory: memory_core.json (human/persona)
第二套风险点: 会话态 conv_state/session_state/session_plans/topic_ledger/
exec_state/chat.json = 同"工作/会话"事实多个 store (P2 收敛面)
