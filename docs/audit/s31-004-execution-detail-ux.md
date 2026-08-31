# S31-004 — Production Execution Detail & Evidence UX

> 日期: 2026-08-31 | 状态: 实施完成

## 1. Execution UX

Conversation Run 卡 (S30-004) 增强为可展开 Execution Detail:
- 默认: Run ID + status (用户可理解: 执行中/完成/失败)
- 点击展开: 真实 stages (人话角色: 产品经理/开发/测试…) + tokens/cost

## 2. Timeline

Run stages 来自真实 progress.json (workflow_runs/{project}/{run}/progress.json):
```
✓ 产品经理 (product-manager) COMPLETED · 14.9s
● 开发 (developer) RUNNING
○ 测试 (tester) pending
```
每项对应真实 stage, 前端不推算。

## 3. Task / 4. Agent / 5. NodeRun

stages 含 role (product-manager/uxui/architect/developer/tester/release)。
**人话映射** ROLE_LABELS: 产品经理/UX设计/架构设计/开发/测试/发布。
NodeRun 级展开 = P1 (Run 实体完整化后)。

## 6. Tool Call

Conversation 已有真实 tool calls 卡 (WORKFORCE EXECUTED 5 ACTIONS, project_status 等)。
Run detail 展开含 stages (真实执行阶段)。

## 7. Artifact

Workspace ArtifactPanel/CodePanel 接真实 /api/artifacts + content (S31-003)。

## 8. Verification

Workspace EvidencePanel 接真实 /api/ops/drill (已有)。
独立 Verification 视图 = P1。

## 9. Evidence

EvidencePanel (opsDrill) 已有真实数据。
Evidence 独立模型 = P1。

## 10. Failure

失败诚实: run status=failed → ✗ 显示 (真实)。
Recovery UX = P1 (依赖 recovery 事件)。

## 11. Recovery

P1 (self_healing/recovery_service 有真实数据, 未投影)。

## 12. Long-running Run

R1788175174725 继续后台 — Run 卡显示 ● RUNNING (真实), 不绑定 watcher。

## 13. Refresh / Reconnect

Run 卡来自 /api/sessions/{id}/runs — 刷新后恢复 (S30-004 已验证)。

## 14. Conversation Integration

```
Natural Language ("排行榜已经修复, 14 测试通过")
  ↓
Run 卡 (Runs | 1 次执行)
  ↓ 点击展开
Execution Detail (stages 人话 + tokens/cost)
```

## 15. Workspace Integration

Workspace profile 按任务切换 (PRD→Artifact, coding→Code, debug→Diff) — S31-003。

## 16. Expert Mode

Run ID 始终可见 (run_id)。内部 module 名不暴露 (ROLE_LABELS 人话)。
完整 Expert 模式 (task_id/node_run_id) = P1。

## 17. Mock/Fake Audit

```
0 fake execution / 0 fake stage / 0 fake completion
stages 全来自 progress.json 真实数据
```

## 18. Test Evidence

```
前端: k9-workspace + tsc 0 (全量待跑)
后端: 1125 passed
```

## 19. Remaining P1/P2

```
P1: Task/NodeRun 级展开 (Run 实体完整化)
P1: Verification/Evidence 独立视图
P1: Expert Mode (完整 ID 链)
P2: Recovery UX 真实投影
```
