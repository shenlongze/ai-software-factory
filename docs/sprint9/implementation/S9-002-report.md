# S9-002 — Factory Console MVP（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6402 + vitest 105
> 目标: AI Factory 从 CLI 工具 → 用户可操作系统 (4 视图 + 审批操作)

## 功能实现（4 视图 + 审批操作）

```
1. Project Dashboard (ProjectsPage 增强):
   project/status + 当前工作流 (workflow_id/name/status) + 当前阶段 (current_stage/status)
   + 进度 (progress %) + 待审批数 — 点击跳工作流详情

2. Workflow View (WorkflowPage 新建):
   workflow 列表 (状态/进度) + 详情: 8 阶段链 (Idea→PM→Product→UX/UI→Arch→Dev→Test→Release)
   每 stage: status/role/artifact (StageSummary)

3. Artifact Viewer (ArtifactsPage 新建):
   6 类型产物 (product/ux_ui/design/code/test/release) 表格
   + 按 project/workflow/type 组合过滤 (修复 useAsync 依赖 [page,type] 真实 bug)

4. Approval 操作 (ApprovalPage 操作化):
   org 审批门区: pending 门列表 + Approve/Reject 按钮 → POST (source=console 审计)
   → 决定后自动刷新; Core 9c 审批只读区保留
```

## API 扩展

```
GET  /api/projects          (增强: workflow/stage/progress 聚合)
GET  /api/workflows         (新: 列表 + 进度聚合)
GET  /api/workflows/{id}    (新: 8 阶段链详情)
GET  /api/artifacts         (新: project/workflow/type 过滤)
GET  /api/approval-gates    (新: org 门清单, status 过滤)
POST /api/approvals/{id}/approve|reject  (新: 唯一写路径, source=console)
     (404 gate 不存在 / 409 已处理 — conflict_status 修复, __init__ 导出)
```

## 前端结构

```
pages/WorkflowPage.tsx (新建) + ArtifactsPage.tsx (新建)
pages/ProjectsPage.tsx (增强) + ApprovalPage.tsx (操作化)
App.tsx (导航 + 工作流/产物) + api/client.ts (approvalGates + POST) + models/types.ts
  (ApprovalGateSummary/ApprovalDecisionSummary/ArtifactSummary/WorkflowSummary/StageSummary)
```

## 测试结果

```
后端: pytest 6402 (6357 + 45: console 217 全绿 + s9_org 集成 30+)
前端: vitest 105 (92 + 13: Workflow 4/Artifacts 4/Approval 重写/client 扩展)
tsc: 零错误
修复: 2 真实 bug (useAsync 依赖 [page,type]/[page]) + 2 TS 类型 (progress/gate comment)
```

## 限制（MVP 范围, 诚实）

```
1. 无项目注册 (Project Adoption → S9-002 原计划调整后未做; 仍 CLI)
2. 无成本视图 (Cost Ledger → S9-004)
3. 审批操作无二次确认 (直接 POST; 可后续加)
4. Console 写路径仅审批决定 (Permission Boundary: 查询只读 + 决定走 org 状态机)
```

## S9-003 接入说明

```
S9-003 (Dart 验证) 不依赖 Console; S9-004 (Cost Ledger) 可在 Console 加成本页;
S9-006 (真实试点) 可通过 Console 审批门操作 + CLI 驱动
```
