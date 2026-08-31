# S32-002 — Conversation Management Production Capability

> 日期: 2026-08-31 | 状态: 实施完成

## 1-3. Existing APIs (审计)

| 能力 | API | 状态 |
|------|-----|------|
| 列表 | GET /api/sessions | ✅ 已有 |
| 创建 | POST /api/sessions | ✅ 已有 |
| 重命名/归档 | PATCH /api/sessions/{id} | ✅ 已有 |
| 历史 | GET /api/sessions/{id}/messages | ✅ 已有 |
| Run 关联 | GET /api/sessions/{id}/runs | ✅ 已有 (S30-003) |
| Search | — | ❌ 无 (P1 Backend capability) |
| Delete session | — | ❌ 无完整 (只有 delete messages, P1) |

## 4. Conversation Data Model

```
Session { id, scope, project_id, title, status(active|archived),
          created_at, updated_at, summary, run_ids[] }
Messages { id, session_id, role, content, created_at }
```

## 5. Lifecycle

```
active → archived (PATCH status) — 已有
active → deleted — 无 (P1 Backend)
```

## 6-8. Association

```
Conversation → Session: 1:1 (Session 是真实 Runtime)
Session → Run: 1:N (run_ids, S30-003)
Session → Project: project_id (company scope = null)
```

## 9. Capability Gaps

```
P1: Search (无 API)
P1: Delete session (无完整 API)
P1: project_id 自动关联 (会话创建时手动指定)
```

## 10. Implemented (本次)

```
- 左栏会话项加重命名 (✎) / 归档 (⎋) 按钮
- 复用 ctx.renameSession / ctx.archiveSession (真实 PATCH)
- 测试 +1 (会话管理, 9/9)
```

## 11. P0/P1/P2

```
P0: 列表/创建/打开/历史/Run 状态 — 已有 (S30-004 验证)
P0: 重命名/归档 — 本次接 UI
P1: Search / Delete (Backend capability)
P1: Conversation Context (project 关联投影)
P2: 会话分组/标签
```

## 12. Reality Audit

```
✅ 列表: GET /api/sessions (真实)
✅ 创建: POST (持久化, 刷新存在)
✅ 打开: selectSession → GET messages (历史恢复)
✅ 重命名: PATCH → refresh (持久化)
✅ 归档: PATCH status=archived (持久化)
✅ Run 状态: GET /api/sessions/{id}/runs (真实)
✅ 并发隔离: 每个 session 独立 (S30-001 多 tab 验证)
❌ Search: 无 API, 前端不做假搜索
❌ Delete: 无 API, 标记 P1
```
