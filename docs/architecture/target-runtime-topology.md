# S30-ARCH — Target Runtime Topology

> 日期: 2026-08-31 | 目标架构 (不执行)

## 目标

```
                    AI Factory
                         │
                ┌────────┴────────┐
                │                 │
             Backend           Runtime
              :8011              │
              (唯一 API)    ┌─────┼──────┐
                │           │     │      │
       ┌────────┼────────┐  Browser Terminal MCP
       │        │        │  (exec 进程内/worker, 不复制 API)
      Web     Desktop   Mobile
    :5180/5173  tauri    flutter(未来)
       │        │        │
       └────────┴───┬────┘
                    ↓
                 API :8011
```

## 原则

1. **API Backend 唯一 (8011)**: API/Session/Conversation/Project/Task/Run/Agent/Artifact/Verification/Evidence/Governance/Event 全部由它负责
2. **UI Dev Servers 独立**: Web (5173 vite / 5180 static), Desktop (tauri dev), Mobile (flutter dev) — 不是 Backend
3. **Execution Runtime 允许独立**: Node Runtime / Executor / MCP / Sandbox — 但**不复制 API Backend**
4. **Worker ≠ Backend**: 任务执行可产生 worker 进程, 不能产生第二个 API

## 收敛目标

```
Development:
  factory start → 8011 (API) + 5180 (static WebUI)   [标准]
  npm run dev   → 5173 (vite, 仅前端开发, /api 代理到 8011)  [可选]
  tauri dev     → desktop → 8011
  flutter run   → mobile → 8011 (未来)

Production:
  factory start → 8011 (API + serve 静态 assets, 5180 合并)
```

## 关键决策 (待确认)

- [ ] 5180 vs 5173 二选一 (开发环境统一)
- [ ] 生产: 5180 合并进 8011 (同一 uvicorn serve 静态) — 减少端口
