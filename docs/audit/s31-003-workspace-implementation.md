# S31-003 — Dynamic Workspace Implementation

> 日期: 2026-08-31 | 状态: 实施完成

## 1. Workspace Definition

Workspace = 当前任务/Conversation/Run 的可视化与操作工作上下文。
**不是** Browser / Run Detail / Dashboard / 文件管理器。动态容器, 由 Context 驱动。

## 2. Workspace Model (当前实现)

```
Workspace (AfWorkspace, V2 保留)
├── context: 来自 ConversationContext (session_id 经 activeId)
├── profile: deriveProfile(sending, lastUserMessage) → prd/coding/debug/qa/default
├── active_view: activeTabId (由 profile 决定默认, 用户可切换)
├── views[]: PROFILE_TABS[profile] 映射的 Tab
└── state: isIdle / sending / ready
```

## 3. View Model

```
WorkspaceView = { id, label, icon } (WsTabDef)
8 个 View: files / artifact / code / terminal / preview / diff / evidence / task
```

## 4. Production Object Mapping

| Production Object | Workspace View | 数据来源 |
|-------------------|---------------|---------|
| Artifact | ArtifactPanel / CodePanel / PreviewPanel | /api/artifacts + /{id}/content |
| Run | (Conversation Run 卡) | /api/sessions/{id}/runs |
| Task | TaskPanel | /api/projects-os/{id}/status |
| Verification | EvidencePanel | /api/ops/drill |
| Approval | ApprovalCard | /api/approvals (真实, 本次修复) |
| File | FilesPanel (本次接真实) | /api/artifacts |

## 5-8. Conversation/Run/Artifact/Verification → Workspace

- profile 由 Conversation 最后用户消息驱动 (PRD→Artifact, coding→Code, debug→Diff)
- Run 状态卡在 Conversation (S30-004), Workspace 由执行状态切换 profile
- Artifact/Verification Panel 接真实 API (S30-001 审计确认)

## 9. Refresh / Recovery

Workspace context 来自 ConversationContext (activeId) — 刷新后由会话恢复驱动。
Tab 选择由 profile 推导 (纯函数), 刷新后自动重算。

## 10. Long-running Run

Run R1788175174725 继续后台 (独立于 Workspace/Browser 生命周期)。
Workspace 显示就绪态, 不绑定 Run 生命周期 (S31-001.5 原则)。

## 11. Responsive

当前: 三栏固定。Workspace 独立 projection, 未来 Mobile 可复用。
(本阶段不做 Mobile)

## 12. API Contract

复用现有: artifacts / artifactContent / approvals / osDecideApproval / osProjectStatus / opsDrill / sessionRuns。
**无新增 API。**

## 13. UI Architecture

```
AfWorkspace
├── Header (Workspace + 上下文状态)
├── Tabs (profile 驱动)
├── ApprovalCard (真实审批)
└── Panels (8 个, 接真实 API)
```

## 14. Test Evidence

```
前端: k9-workspace 6/6 + tsc 0
后端: 1125 passed
浏览器: 待验证 (build 后)
```

## 15. Remaining P1/P2

```
P1: Terminal Panel (真实终端集成)
P1: Workspace 上下文标题增强 (当前任务名)
P2: Mobile Workspace
```
