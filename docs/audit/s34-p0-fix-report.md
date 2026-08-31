# S34-P0-FIX — Production Core Convergence 完成报告

> 日期: 2026-09-01 | 真实 E2E 证据

## 1. Architecture(已收敛)

```
Conversation → Production Core → Project → Requirement → Plan → Approval → Task → Run
     ↓              ↓              ↓         ↓           ↓       ↓        ↓      ↓
  send_message  ConsoleService  org SSOT  requirements  session_plans  approvals  backlog  progress
```

## 2. P0 修复

```
P0-1 Project API:    GET /api/projects/{id} (上轮) + /plan + /progress (本轮) ✅
P0-2 Project 收敛:    create_project → ConsoleService Core (上轮) ✅
P0-3 Plan Artifact:  plan_id + version/architecture/milestones/dependencies/risks/task_ids
                     + project_id 关联 (company 会话 AI 显式传参) ✅
P0-4 Approval 关联:  subject_ref=plan_id (双向可追溯) ✅
P0-5 Run 关联:       progress.json 写 task_id/plan_id/session_id ✅
Import:              POST /api/projects/import (复用 cmd_project_register) ✅
```

## 3. Reality Matrix

| Capability | CLI | API | Web | Conversation | SSOT | REAL |
|-----------|-----|-----|-----|-------------|------|------|
| Create Project | ✅ | ✅ | ✅ | ✅ | org | REAL |
| Import Project | ✅ | ✅ 新增 | ⚠️ | - | org | PARTIAL |
| Requirement | ✅ | ✅ | ⚠️ | ✅ | requirements.json | REAL |
| Plan | ⚠️ | ✅ /plan | ✅ 卡片 | ✅ plan_id | session_plans | REAL |
| Approval | ✅ | ✅ | ⚠️ | ✅ subject_ref | approvals.json | REAL |
| Task | ✅ | ✅ | ⚠️ | ✅ plan_id | backlog | REAL |
| Run | ✅ | ✅ | ✅ | ✅ task/plan/session | progress.json | REAL |
| Monitoring | ✅ | ✅ /progress | ⚠️ | ✅ | progress.json | PARTIAL |
| Cost | ✅ | ✅ | ✅ | ✅ | totals | REAL |
| Workspace | - | ✅ | ✅ | - | projection | REAL |

## 4. Data Truth Matrix

| Object | SSOT | Writer | API | CLI | Web |
|--------|------|--------|-----|-----|-----|
| Project | org/projects.json | ConsoleService | GET/POST/import | projectos | ProjectWorkspace |
| Requirement | requirements.json | plan_development | 详情返回 | - | progress-card |
| Plan | session_plans.json | plan_development | /plan | - | progress-card |
| Approval | approvals.json | request_approval | /approvals | approval | - |
| Task | backlog task.json | execute_plan | backlog | tasktree | 任务面板 |
| Run | progress.json | workflow_runner | /runs | production | Run 卡 |
| Session | console_sessions | send_message | /sessions | - | 左栏 |

## 5. E2E Evidence

```
用户: "给飞机大战项目出开发计划"
→ project_list (查 P-b0adfaa6) + plan_development (project_id=P-b0adfaa6)
→ plan_01262486eed4 | project_id=P-b0adfaa6 | approval appr-c8f0751e13
→ 9 任务 (P0/P1/P2) | 完整字段 (version/architecture/milestones/risks)
→ GET /api/projects/P-b0adfaa6/plan → count:1 真实查询 ✅
```

## 6. 验证

```
✅ 后端: 1154 passed + 4 skipped
✅ 专项: 29/29 (含 plan 完整字段 / approval subject_ref)
✅ 前端: 518/519 (af-todo-tree PRE-EXISTING/DEFERRED)
✅ tsc | build: PASS
✅ git clean (commit ff4ca897)
```

## 7. Final Verdict

```
P0-1 Project API:      VERIFIED
P0-2 Project 收敛:      VERIFIED
P0-3 Plan Artifact:    VERIFIED (真实查询)
P0-4 Approval 关联:    VERIFIED
P0-5 Run 关联:         VERIFIED
Conversation→Core 链:  REAL
```
