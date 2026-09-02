# DATA LINEAGE — STEP 4 (2026-09-02)

## 真实 ID 链 (运行时数据)

| Entity | 真实 ID | Storage | 引用 |
|--------|---------|---------|------|
| Requirement | req_33846c95b001 等 7 条 | requirements.json | session_id, project_id |
| Session | sess-* (81) | console_sessions.json | — |
| Project | P-b0adfaa6 等 | org/projects.json | requirement.project_id |
| Plan | PLAN-* | session_plans.json | project_id, session_id |
| Task | TASK-* (backlog) | task.json | plan_id |
| Run (exec) | EXS-* | exec/execution_records.json | agent_id, task(T001/T002) |
| Artifact | ART-* | exec/results.json | task_id, agent_id, event_refs |
| Audit | event ids | audit_events.json | session/project |

## 断点

| 断点 | 证据 |
|------|------|
| Requirement → Plan/Task | requirements.json 无 plan/task 引用字段 (仅 project/session/title) |
| 会话链 Task → Artifact | backlog Task 无 artifact_ref (exec 系统 Artifact 与 backlog 不关联) |
| exec Task (T001/T002) vs backlog Task (TASK-*) | 两套 task id 前缀 — 不同 task 域 |
| Plan → Requirement | session_plans 无 requirement_id |

## exec 任务域 vs 会话任务域

- exec: task_id = T001/T002 (execution_records/artifacts)
- 会话链: task_id = TASK-* (backlog)
- M3: task_id = T-* 或 legacy
→ 三套 task 标识并存 (证据: artifacts task=T002 vs backlog TASK-*)
