# S35-P0-FIX — Project Management Contract & One Execution Path 完成报告

> 日期: 2026-09-01 | 真实 E2E 证据

## 1. P0 修复

```
P0-A: Project Git Contract
      Project model +7 字段: git_enabled / git_repo_url / git_provider /
      git_default_branch / git_current_branch / git_head_commit / git_working_tree
      → 详情 API + workspace API 实时探测 (git enabled=false 诚实)

P0-B: repo_path 修复
      创建项目后回写真实工作目录 (workspace/projects/{slug})
      → 不再错误指向 ~/.factory 根
      → 实测: 新项目 repo_path=workspace/projects/P-xxx

P0-C: Workspace API 修复 404
      根因: 读 projects/{id} (旧路径) vs 实际 workspace/projects/{slug}
      → slug 解析 (ProjectSpaceStore.get_slug) + 旧兼容 fallback
      → 实测: draft (slug=unnamed-...) 与正式项目均返回真实 root

P0-D: Requirement 关联
      GET /api/projects/{id}/requirements (Project 1—N Requirement)
      + /plans + /tasks 端点 (完整 API Contract)
      → 实测: 飞机大战 requirements 6 / tasks 20 / plans 4
```

## 2. API Contract 现状

```
✅ GET /api/projects | POST /api/projects | GET /api/projects/{id}
✅ POST /api/projects/import
✅ GET /api/projects/{id}/workspace (+git)
✅ GET /api/projects/{id}/requirements (新增)
✅ GET /api/projects/{id}/plans (新增)
✅ GET /api/projects/{id}/tasks (新增)
✅ GET /api/projects/{id}/runs | /artifacts | /status | /plan | /progress
❌ PATCH/DELETE /api/projects/{id} (P2)
```

## 3. 真实 E2E

```
创建 (有 name): P-3f03609b → workspace/projects/s35 存在
  → repo_path 回写 | workspace API 真实 root ✅
创建 (draft): P-05cc8230 → workspace/projects/unnamed-... 存在
  → slug 解析 workspace API 200 ✅
飞机大战: workspace root 真实 | requirements 6 | tasks 20 | plans 4 ✅
Git: 全部 enabled=false 诚实 (未初始化不伪造) ✅
```

## 4. 验证

```
✅ 后端: 1158 passed + 6 skipped
✅ 专项: 35/35 (+2 Git 字段/repo_path, subprocess 隔离)
✅ 前端: 518/519 (af-todo-tree DEFERRED)
✅ tsc | build: PASS
✅ git clean (commit ff52cdc8)
```

## 5. 最终评级

```
One Execution Path:   VERIFIED (全部走 ConsoleService)
Single Source of Truth: VERIFIED (org + workspace 目录信源)
Project Contract:     VERIFIED (25+7 字段)
Workspace Contract:   VERIFIED (slug 解析 + git)
Git Contract:         VERIFIED (7 字段 + 实时探测)
Requirement Contract: VERIFIED (/requirements 端点)
Plan Contract:        VERIFIED (/plans)
Approval Contract:    VERIFIED (subject_ref)
Task Contract:        VERIFIED (/tasks + plan_id)
Run Contract:         PARTIAL (两套体系 P1)
Artifact Contract:    PARTIAL (P1)
Web → API only:       VERIFIED (前端调 api.projects)
Conversation → Core only: VERIFIED (工具走 dispatch)
```

## 6. 剩余 P1/P2

```
P1: 两套 Run 体系统一 / 历史 task plan_id 补全 / CLI project show
P2: PATCH/DELETE /api/projects/{id} / Web Git 视图 / Artifact 反查
```
