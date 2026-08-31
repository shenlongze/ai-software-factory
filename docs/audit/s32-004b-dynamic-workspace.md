# S32-004B — Project → Dynamic Workspace 真实触发 (深化)

> 日期: 2026-08-31 | 状态: 完成

## 链路定位(真实根因)

```
Project click
  → AfContextNav.onSelectProject(id)     ✅ (S32-004A 已接)
  → Shell → ctx.setProjectId(id)          ✅ (S32-004B 已接)
  → AfWorkspace 消费 ctx.projectId        ← 本次深化: 小卡 → 完整切换
```

上一版只显示小 Context 卡;本次把右栏**主体**切换为 Project Workspace。

## 唯一 Selection State

```
selectedProjectId = ConversationContext.projectId (唯一)
  AfContextNav 写 → Shell 回调
  AfWorkspace 读 → 渲染 ProjectWorkspace
无重复 state / 无 localStorage Truth / Backend = 数据 Truth
```

## Workspace 切换

```
ctx.projectId ? <ProjectWorkspace> : <默认 Workspace (Tab 面板)>
```

## ProjectWorkspace (真实数据)

```
① osProjects → title/status/id (项目信息)
② osProjectStatus → progress (completed/running/failed/total) + sprints[].tasks (最近任务)
③ projectRuns → 当前执行 (run_id/status)
```

## API

```
GET /api/projects-os           (项目基本信息)
GET /api/projects-os/{id}/status (真实 progress/tasks)
GET /api/projects/{id}/runs    (真实 workflow_runs, S32-004)
```

## Conversation 为何不被破坏

```
项目点击只改 ctx.projectId (Context state)
中央 ConversationCenter 不订阅 projectId → 历史/Session/Runtime 完全不变
```

## Refresh 恢复

```
URL #/workspace?project=id
→ parseHash → ConversationProvider initialProjectId
→ ctx.projectId → ProjectWorkspace 重新请求 Backend
```

## Clear

```
✕ 清除 → ctx.setProjectId(null) → 默认 Workspace (Conversation 不变)
```

## 独立 Project navigation

```
#/project/{id} 仍保留 (深度项目工作区: 任务/文档/质量)
?project= 是 Context 选择; 二者互补
```

## 重复 Project state

```
无 — 唯一 ConversationContext.projectId
```

## 验证

```
后端 1125 passed
前端 512/513 (af-todo-tree 历史漂移)
k9 12/12 (Project Workspace 完整)
tsc PASS
```
