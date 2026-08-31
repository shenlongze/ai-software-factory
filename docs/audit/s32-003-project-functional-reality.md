# S32-003 — Project Core Functional Completion

> 日期: 2026-08-31 | 状态: 实施完成

## 1. Existing Project APIs (审计)

| 能力 | API | 状态 |
|------|-----|------|
| 列表 | GET /api/projects + GET /api/projects-os | ✅ |
| 创建 | POST /api/projects (idea/name) | ✅ |
| 打开 | GET /api/projects/{id} | ✅ |
| 更新 | PATCH /api/projects/{id} | ✅ |
| 删除 | DELETE /api/projects/{id} | ✅ 有 (前端未接, 保守) |
| 任务 | backlog/epic + task detail | ✅ |
| 文档 | GET /api/projects/{id}/docs | ✅ |
| 产物 | GET /api/projects/{id}/artifacts | ✅ |

## 2. Existing Project Model

```
Project { id, name, status(idea/confirmed/development...), workflow_status,
          current_stage, progress, tasks{}, created_at, updated_at }
```

## 3-5. Task/Run/Conversation

```
Task: backlog API (createBacklogFeature/updateBacklogTask) ✅
Run:  GET /api/sessions/{id}/runs + workflow_runs progress ✅
Project↔Conversation: session.project_id (company scope = null) ⚠️
```

## 6. Implemented UI (本次)

```
- 左栏项目块: ＋ 新建项目 (真实 POST /api/projects, prompt idea)
- 项目列表: 显示 status 徽章 (真实)
- 创建后: loadProjects 刷新 (持久化可见)
```

## 7. Backend capability gaps

```
⚠️ Project↔Conversation: session 创建时可指定 project_id, 但 company 会话无关联
P1: 项目创建后自动关联当前会话
P1: Project Delete UI (API 有, 前端未接 — 保守)
```

## 8. P0/P1/P2

```
P0: 列表/创建/打开/状态 — 全部真实 ✅
P1: Project↔Conversation 关联投影
P1: Delete UI (API 已有)
P2: 项目搜索/分析
```

## 9. Reality verification

```
✅ 列表: GET /api/projects-os (真实, 含 status)
✅ 创建: POST /api/projects → 刷新 → 项目存在 (持久化)
✅ 打开: AfProjectHome fetch /api/projects/{id}
✅ Progress: 真实 workflow_state (不伪造百分比)
✅ Tasks: backlog API (真实)
❌ 不做: 假 Search / 假 Delete 按钮 / 假百分比
```

## 验证

```
tsc PASS
前端: 510 过 (af-todo-tree 历史漂移)
后端: 1125 passed
```
