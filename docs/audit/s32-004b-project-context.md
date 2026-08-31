# S32-004B — Contextual Project Selection & Dynamic Workspace

> 日期: 2026-08-31 | 状态: 实施完成

## 核心变化

```
之前 (S32-004A): 点击项目 → navigate(#/project/{id}) → 离开 Workbench (独立页)
现在 (S32-004B): 点击项目 → setProjectId → 保持 Workbench → 右栏显示项目 Context
```

## 实施

### 1. URL 策略

```
#/workspace?project={id} → workspace 级 + project context (不再重定向独立页)
Refresh → parseHash 读 query → initialProjectId → ConversationContext 恢复
```

### 2. Context 注入

```
App.tsx: ConversationProvider initialProjectId={route.projectId}
Shell:   挂载时 ctx.setProjectId(initialProjectId) (URL 恢复)
```

### 3. 项目点击

```
AfContextNav.onSelectProject(id) → ctx.setProjectId(id) + hash ?project=id
→ 中央 Conversation 不离开 (仍是唯一 Runtime)
→ 右栏 Workspace 显示 Project Context 卡
```

### 4. 右栏 Project Context 卡

```
真实加载: api.osProjects() 按 id 查 → title/status/id
含: 清除按钮 (ctx.setProjectId(null) → Workspace 恢复默认)
```

## 产品边界 (落实)

```
Conversation: 意图/自然语言 (不离开)
Project:      当前工作 Context (选择, 非页面)
Workspace:    Context 可视化 (右栏投影)
Backend:      Production Truth
```

## 验证

```
tsc PASS
前端: 12/12 (k9, +1 Project Context)
浏览器: 待实测 (项目点击 → 右栏 Context, 不离开 Workbench)
```

## 遗留

```
#/project/{id} 独立页仍保留 (深度项目工作区, 如任务管理/文档)
?project= 是 Context 选择; #/project/ 是完整项目工作区 — 二者互补
```
