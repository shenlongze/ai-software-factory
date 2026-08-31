# S35-PROJECT-MANAGEMENT-CONTRACT — Project Management 数据契约审计

> 日期: 2026-09-01 | 纯审计 (禁止修复) | 真实代码 + API + 存储证据

## 1. Project 数据模型 (org Project schema)

```
25 字段 (factory-org/org/projects.py Project):
  id / name / user_id / goal / starred / archived / lifecycle
  repo_path / language / framework / build_command / test_command
  project_type / analysis_ref / baseline_ref / snapshot_ref
  slug / draft / company_id / department_ids / discovery / bindings
  metadata / created_at / updated_at

缺失字段 (5 个):
  ❌ git_enabled / git_repo_url / git_branch / git_HEAD 等 Git 字段
  ❌ requirement_id (Project↔Requirement 无字段关联)
  ❌ workspace_path (Project Root / Workspace Path 未显式建模)
  ❌ progress (实时进度不存 Project)
  ❌ stage (用 lifecycle 替代)
```

## 2. Identity / Lifecycle / Workspace

```
Identity: id/name/slug ✅ | description ❌ (用 goal 替代)
Lifecycle: lifecycle (idea→development 状态机) ✅ | created/updated ✅ | archived ✅
Workspace: 无 workspace_path 字段 — repo_path 存在但实际全为 "/Users/agentdev/.factory" (非真实路径!)

真实抽样 (5 项目):
  P-b0adfaa6 飞机大战: dir✅ ws✅ git❌ repo_path=/.factory (错)
  P-f848f51d 日记:     dir✅ ws✅ git✅ repo_path=/.factory (错)
  P-5be3a04a 番茄钟:    dir✅ ws✅ git❌ repo_path=/.factory (错)
  ai-factory-self:     dir✅ ws✅ git❌ repo_path= (空)
  P-e023a04c 墨笺:     dir✅ ws✅ git❌ repo_path=/.factory (错)
→ repo_path 全部错误/空 (未反映真实工作目录)
```

## 3. Git / Repository Contract — MISSING

```
❌ Project model 无任何 git 字段
❌ GET /api/projects/{id}/git 端点不存在
✅ 详情 API repository 字段: {status: not_initialized, path} (只探测 .git 目录)
❌ git_repo_url / git_branch / git_HEAD / git_remote 全部无法回答
```

## 4. Project ↔ Workspace — PARTIAL

```
✅ create_project 建空间骨架 (S34-P0-D 已修)
✅ workspace/projects/{id}/ 存在 (抽样 5/5)
✅ project.json / management/ 骨架
⚠️ GET /api/projects/{id}/workspace → 404 "project workspace not found"
   (workspace 端点契约不完整)
⚠️ Import 无 workspace 映射
```

## 5. Project ↔ Requirement — PARTIAL

```
✅ requirements.json: 7 条, 6 条绑定 P-b0adfaa6
⚠️ req_0862000369e0 project_id 空 (早期创建无绑定)
❌ Project model 无 requirement_id 反向引用
✅ 详情 API requirements 返回
```

## 6. Project ↔ Plan — REAL (上轮已修)

```
✅ plan_id + project_id + requirement_id + approval_id (session_plans)
✅ GET /api/projects/{id}/plan
⚠️ 早期 plan 无关联 (旧数据)
```

## 7. Project ↔ Approval — REAL

```
✅ approvals.json: 7 条, subject_ref=plan_id
✅ appr-6d19bc318e APPROVED (plan_c35c6c3a1b2b)
⚠️ approval 无 project_id 字段 (通过 plan 反查)
```

## 8. Project ↔ Task — PARTIAL

```
✅ Task.plan_id 字段 (S34/S35-P0-4 已修)
✅ 8 个新任务带 plan_id
⚠️ 12 个旧任务无 plan_id (历史)
⚠️ Task 无 requirement_id 字段
⚠️ GET /api/projects/{id}/tasks 端点不存在 (用 progress 替代)
```

## 9. Project ↔ Run — PARTIAL

```
✅ workflow_runs/{project}/{run}/progress.json
✅ GET /api/projects/{id}/runs
⚠️ exec_state (chain) 独立于 workflow_runs — 两套 Run 体系
⚠️ Run 无 requirement_id
```

## 10. Project ↔ Artifact — PARTIAL

```
✅ GET /api/projects/{id}/artifacts/version
⚠️ Artifact 反查 project/task/run 不完整
```

## 11. Project ↔ Conversation — REAL (上轮已修)

```
✅ Context Resolution: company 不猜项目, create_project 真实
✅ project_list / project_status 工具
✅ P0-5 自动注入 project_id
```

## 12. Import Project — PARTIAL

```
✅ POST /api/projects/import (复用 cmd_project_register)
⚠️ 无 workspace/git 映射建立
⚠️ 无 Web UI 入口
```

## 13. Project API Contract

```
✅ GET  /api/projects
✅ POST /api/projects
✅ GET  /api/projects/{id}
✅ POST /api/projects/import
✅ GET  /api/projects/{id}/status (monitor)
✅ GET  /api/projects/{id}/runs
✅ GET  /api/projects/{id}/artifacts/version
✅ GET  /api/projects/{id}/workspace (但 404 bug)
✅ GET  /api/projects/{id}/plan (上轮)
✅ GET  /api/projects/{id}/progress (上轮)
❌ PATCH /api/projects/{id}
❌ DELETE /api/projects/{id}
❌ GET  /api/projects/{id}/tasks
❌ GET  /api/projects/{id}/plans (用 /plan 替代)
❌ GET  /api/projects/{id}/git
```

## 14. CLI Contract — PARTIAL

```
✅ factory projectos (create/status/replan/approve)
❌ factory project show <id> (无完整详情)
❌ factory project import
❌ factory project tasks/plans/runs/workspace/git
```

## 15. Web Project Management — PARTIAL

```
✅ 前端调 api.projects() (AfProjectShell)
✅ ProjectWorkspace 显示名称/状态/进度
❌ 无 Git 展示 (无 API)
❌ 无 Requirement/Plan/Approval 视图
❌ 无 Artifact/Verification 视图
```

## 16. Project Detail 页面缺口

```
能看到: ID/Name/Progress/Stage/Description (用户反馈)
缺:     Workspace path / Git / Requirement / Plan / Approval / Tasks / Runs / Artifacts
```

## 17. P0/P1/P2

```
P0:
  A1: Project model 缺 Git 契约 (git_enabled/repo_url/branch/HEAD)
  A2: repo_path 全部错误 (/Users/agentdev/.factory 非真实路径)
  A3: GET /api/projects/{id}/workspace 404 (Workspace 断链)
  A4: Project↔Requirement 无 model 关联 (req project_id 空案例)
P1:
  B1: 两套 Run 体系 (exec_state vs workflow_runs)
  B2: GET /api/projects/{id}/tasks + /git 缺失
  B3: 历史 task 无 plan_id / req 无 project_id
  B4: CLI project show/import/tasks 缺失
P2:
  C1: PATCH/DELETE /api/projects/{id}
  C2: Web Git/Requirement/Plan 视图
  C3: Artifact 反查完整化
```

## 18. 最终评级

```
Project Data Model:   PARTIAL (缺 Git/workspace_path/requirement)
Git Contract:         MISSING
Workspace Contract:   PARTIAL (404 bug)
Requirement↔Project:  PARTIAL
Plan/Approval:        REAL
Task:                 PARTIAL (历史无 plan_id)
Run:                  PARTIAL (两套体系)
Artifact:             PARTIAL
API Contract:         PARTIAL (缺 tasks/plans/git/patch/delete)
CLI Contract:         PARTIAL
Web Project Mgmt:     PARTIAL
最终: NOT READY (P0 存在)
```
