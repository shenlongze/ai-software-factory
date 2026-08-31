# S34-P0-PRODUCTION-CONVERGENCE — 全链路收口 Reality Audit

> 日期: 2026-09-01 | 纯审计 (不修改) | 真实代码 + API + 存储证据

## 1. 数据真相全景

```
✅ 项目创建: CLI(projectos) / API(POST /api/projects) / Web(create_project 工具)
           → 全部 ConsoleService Core (org 体系) — 已收敛
✅ Requirement: requirements.json (req_xxx, session/project 绑定) — C5 已修
✅ Approval: governance/approvals.json (appr-xxx PENDING) — C3 已修
✅ Progress: session_progress/ + 前端渲染 — C4 已修
❌ Plan: session_plans.json 孤立文本 (无 plan_id/project_id/task_ids/approval_id)
❌ Task: 无 backlog/task-tree 落库关联
❌ Run: 无 workflow_runs (飞机大战无 run)
```

## 2. P0 Findings

```
P0-A: GET /api/projects/{id} → 405 Method Not Allowed
      (项目详情 API 不存在 — 前端/CLI 无法查项目完整信息)
P0-B: Plan 不是关联 Artifact
      session_plans: {goal, tasks, order, acceptance}
      无 plan_id / project_id / requirement_id / approval_id / task_ids
      → 用户问"飞机大战的项目计划"无法查询真实 Plan 对象
P0-C: execute_plan 建任务无 project 目录 (P-b0adfaa6 无 backlog)
      (task 落库走 service.create_task 但项目目录未初始化)
P0-D: 项目创建无目录/Git 初始化
      14 项目中 6 个无目录 (含飞机大战 P-b0adfaa6), 仅 1 个有 .git
      → Project Management 看不到完整项目
P0-E: Plan→Approval→Task→Run 无链
      plan(孤立) → approval(有) → task(无) → run(无)
```

## 3. Reality Matrix

| Capability | CLI | API | Web | Conversation | SSOT | REAL |
|-----------|-----|-----|-----|-------------|------|------|
| Create Project | ✅ projectos | ✅ POST /projects | ✅ 工具 | ✅ | org | REAL |
| Import Project | ❌ | ❌ | ❌ | ❌ | - | MISSING |
| Requirement | ⚠️ | ⚠️ | ⚠️ | ✅ 落盘 | requirements.json | PARTIAL |
| Plan | ❌ | ❌ | ❌ | ⚠️ 孤立文本 | session_plans | PARTIAL |
| Approval | ✅ | ✅ | ⚠️ 无 UI | ✅ | approvals.json | REAL |
| Task | ✅ tasktree | ✅ backlog | ⚠️ | ⚠️ | task.json | PARTIAL |
| Run | ✅ production | ✅ /runs | ✅ 卡 | ✅ | progress.json | REAL |
| Monitoring | ✅ | ✅ monitor | ⚠️ 简化 | ⚠️ 文本 | progress.json | PARTIAL |
| Cost | ✅ | ✅ | ✅ usage | ✅ | progress totals | REAL |
| Workspace | - | ✅ | ✅ | - | projection | REAL |

## 4. Data Truth Matrix

| 对象 | SSOT | Writer | API | CLI | Web Projection |
|------|------|--------|-----|-----|---------------|
| Project | org/projects.json | ConsoleService | POST/GET(缺) | projectos | ProjectWorkspace |
| Requirement | requirements.json | plan_development | 无 | 无 | 无 |
| Plan | session_plans.json | plan_development | 无 | 无 | progress-card |
| Approval | approvals.json | request_approval | /api/approvals | approval | 无 UI |
| Task | task.json/backlog | execute_plan | backlog | tasktree | 任务面板 |
| Run | progress.json | workflow_runner | /runs | production | Run 卡 |
| Session | console_sessions | send_message | /api/sessions | - | 左栏 |

## 5. 根因

```
plan_development/execute_plan 是"会话助手"路径:
  - Plan 只写 session_plans.json (无 ID/关联)
  - Task 建 backlog 但项目目录未初始化 (create_project 只写 org)
  - 无项目详情 API (前端无法完整展示)
Conversation 与 Project Management 之间缺统一 Plan/Task 关联层
```

## 6. 停止

发现 P0 (A/B/C/D/E) → 停止, 报告完毕, 不进入 P1/P2。
