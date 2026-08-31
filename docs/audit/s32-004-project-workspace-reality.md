# S32-004 — Project Workspace Reality Integration

> 日期: 2026-08-31 | 状态: 实施完成

## 1-5. API Inventory (审计)

| 能力 | API | 状态 |
|------|-----|------|
| Project | GET /api/projects, /api/projects/{id} | ✅ |
| Project status | /api/projects/{id}/workspace, /monitor | ✅ |
| Project tasks | /api/projects/{id}/backlog | ✅ |
| Task status | PATCH backlog task | ✅ |
| **Project runs (新)** | **GET /api/projects/{id}/runs** | ✅ 本次新增 |
| Run stages | workflow_runs/{project}/{run}/progress.json | ✅ |
| Artifact | /api/artifacts + /{id}/content | ✅ |
| Verification | /api/ops/drill | ✅ |
| Project↔Conversation | session.project_id | ⚠️ PARTIAL |

## 6. Capability Matrix

| Project Workspace | 能力 | Reality |
|-------------------|------|---------|
| 当前状态 | workspace/lifecycle/monitor | REAL |
| 生命周期 | lifecycle stages | REAL |
| Tasks | backlog | REAL |
| **Runs (本次)** | **/api/projects/{id}/runs** | **REAL (新)** |
| Artifacts | artifacts API | REAL |
| Verification | opsDrill | REAL |

## 7. REAL/PARTIAL/MISSING

```
REAL:    状态/生命周期/任务/Run/Artifact/Verification
PARTIAL: Project↔Conversation (session.project_id, company 会话无关联)
MISSING: 无 (Project Home 核心能力全部真实)
```

## 8. Implemented (本次)

```
- 后端: GET /api/projects/{id}/runs (workflow_runs 真实 progress)
- 前端: AfProjectHome 执行记录块 (run_id/status/tokens/时间, 真实)
- 类型: ProjectRunSummary
- 轮询: 复用 loadAll 15s (Run 状态实时)
```

## 9. Remaining Gaps

```
P1: Project↔Conversation 关联投影
P1: Run → Execution Detail 点击展开 (复用 S31-004)
P2: Artifact/Verification 独立投影块
```

## 验证

```
后端: 1125 passed + 新端点真实 (P-69c4f155 → 2 runs)
前端: tsc 0 (全量待跑)
真实: GET /api/projects/P-69c4f155/runs → R1788175174725/running + R1788174921245/running
```
