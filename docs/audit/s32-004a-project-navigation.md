# S32-004A — Fix Project Navigation Dead Interaction

> 日期: 2026-08-31 | 状态: 修复完成

## 1. 复现

```
点击左栏「项目」下「台球计分演示」→ 无任何反应
(URL 不变 / 页面不变 / console 无报错)
```

## 2. 根因(两层)

### 层 1: 左栏点击不导航

```
AfWorkspaceShell 传 AfContextNav 时没传 onSelectProject
→ 项目点击回调 undefined → 什么都不发生
```

### 层 2: 双项目源(点击后 404)

```
左栏列表: /api/projects-os → project_os (org/projects.json)
项目页:   AfProjectShell api.projects() → console.service (workspace/projects/)
→ OS 项目在 console 项目源查不到 → "项目不存在"
```

## 3. 修复

### 修复 1: Shell 传导航回调

```
AfWorkspaceShell:
  onSelectProject={(id) => navigate(`#/project/${encodeURIComponent(id)}`)}
  onSelectConversation={() => navigate('#/workspace')}
→ 项目点击 → hash 变化 → App hashchange → AfProjectEntry
```

### 修复 2: AfProjectShell 双源兼容

```
找不到 console 项目 → fallback api.osProjects() 按 id 查
→ OS 项目映射为 ProjectSummary (name=title, status)
→ 真实打开项目工作区
```

## 4. 真实验证

```
✅ 点击项目 → URL: #/project/project_043d829351f3 (真实 ID)
✅ Project 导航 7 子页渲染 (概览/文档/任务/执行/运行时/质量/运维)
✅ OS 项目 fallback: 台球计分演示 → 项目工作区
✅ Refresh: projectId 从 URL 读 → 重新请求 → 项目仍在
❌ 不存在项目: 保持 "项目不存在或已被删除" (真实 404, 不伪造)
✅ 返回: ← 返回工作台 → #/workspace → 列表正常
```

## 5. 验证

```
tsc: PASS
前端测试: 6/6 (shell/entry) + 11/11 (k9)
build: PASS
后端: 1125 passed
```

## 6. 关键教训

**双项目源**(projects-os vs /api/projects)是历史遗留(OS 项目 vs console 项目)。
本项目用 fallback 兼容;后续 S32 应统一项目源(单 SSOT)。
