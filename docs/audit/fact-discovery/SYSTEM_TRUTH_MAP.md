# SYSTEM TRUTH MAP — FACT DISCOVERY (2026-09-02)

> 实体 × {Fact/Projection, SSOT, Storage, Writers, Derived} — 由代码写点/读点证据产生。

| Entity | Fact/Proj | SSOT | Storage | Writers (代码) | Derived From |
|--------|-----------|------|---------|----------------|--------------|
| Project | Fact | org/projects.json | ProjectStore | ProjectLifecycle.create_project | — |
| Idea | Fact(会话消息) | console_sessions.json | SessionStore | POST /messages | — |
| Requirement | UNKNOWN(未审计到持久化实体) | ? | ? | product_intelligence(返回 markdown 不落盘) | ? |
| Brainstorm | UNKNOWN | ? | ? | discovery_intelligence(conversation.json) | ? |
| PRD | UNKNOWN | ? | ? | 未定位到结构化 PRD 实体 | ? |
| Plan | Fact | session_plans.json | PendingPlanStore | plan_development/execute_plan/reconcile_plan | — |
| Task | Fact | backlog/task.json | ManagementStore | create_task/transition_task/finish_task_exec | Plan |
| Task.dependency | Fact | backlog (同文件) | ManagementStore | create/update_task | — |
| ExecState | Projection | session_exec/{sid}.json | ExecState | chain_start/execute_plan/next/recover | Task+backlog |
| Run | Fact | ExternalTaskRegistry | registry | gateway_execute | Task |
| BLOCKED | Derived | — | ExecState 投影 | ExecState.next | dependency+failed |
| READY/WAITING | Derived | — | — | ExecState.next | dependency |
| UNKNOWN | Marker | ExecState 任务 verify | — | recover | Run 证据缺失 |
| Artifact | Fact | invocation store (result_id) | _exec.record_invocation | gateway | Run |
| Verification | Fact | invocation store + task verify | _verify_output | gateway | Artifact |
| Event | Fact | audit/audit_events.json | AuditEmitter | 各写路径 | — |
| Audit | Record | audit/audit_events.json | AuditStore | audit | — |
| Session | Fact | console_sessions.json | SessionStore | SessionStore | — |
| Agent(profile) | Fact | agents.json | — | API | — |
| Skill | Fact | skills.json | — | API | — |
| Provider/Model | Fact | factory-core providers store | registry | core CLI | — |
| Release | Fact | (releases.json?) | ? | POST /api/releases | UNKNOWN |
| Experience/Learning | Fact | (learning store?) | ? | POST /api/learning | UNKNOWN |

## 风险记录 (fact 级, 非判断)

- Requirement/Brainstorm/PRD 持久化实体: 本扫描未定位到独立文件 (product_intelligence action 返回 markdown)
- factory-core 的 providers/product/understanding 有独立 store, 但 console 不 import → 双数据域
- factory-exec 员工执行器系统独立, 未发现 console 调用
