# S31-005 — Client Architecture & Module Boundary Audit

> 日期: 2026-08-31 | 纯审计 (零修改) | 依据: 真实代码/进程

---

## 一、真实 Client 拓扑

```
Web (React 18 + Vite)
  ├── src/
  │   ├── api/client.ts (唯一, 115 方法)
  │   ├── api/runtimeClient.ts (SSE 封装)
  │   ├── components/af/ (三栏: ContextNav/ConversationCenter/Workspace)
  │   ├── models/ (domain.ts + types.ts)
  │   ├── state/ (AppState + workspace)
  │   ├── hooks/ (useAsync)
  │   ├── utils/ (wireframe)
  │   ├── shell/ (旧组件, 半死)
  │   ├── mock/ (测试用, 生产零引用 ✅)
  │   └── design/ (theme/tokens)
  │
Desktop (Tauri 2, Rust)
  ├── src-tauri/src/
  │   ├── main.rs (Shell: 启动/关闭 factory-runtime)
  │   ├── runtime.rs (start/stop/status/logs — 调 factory-runtime CLI)
  │   └── launcher.rs (启动器窗口)
  ├── src/ui/ (launcher.html/css/js — 非 React WebUI)
  └── capabilities (最小权限 core:default)

Mobile: 不存在
```

## 二、端口架构 (真实)

```
8011 = Backend API (唯一)
5180 = Production/Static Web (factory start serve dist)
5173 = Dev Server (vite, 手动)
```

## 三、Client Boundary (结论)

| Client | 职责 | 证据 |
|--------|------|------|
| Web | 完整 UI (三栏) + Browser 能力 | frontend/src |
| Desktop | Shell 宿主 + Native 能力, **不重写 UI** (launcher 只是启动器) | main.rs "永远不是业务层" |
| Mobile | 未来 Client, 当前不存在 | — |

## 四、Anti-pattern Audit (全部干净 ✅)

```
❌ Client 维护 Production Truth → 无 (UI 全走 API)
❌ Web/Desktop 双事实 → 无 (desktop 无业务逻辑)
❌ API client duplication → 无 (client.ts 唯一)
❌ Conversation duplication → 无 (8 组件共用 ConversationContext)
❌ Workspace duplication → 无 (AfWorkspace 唯一)
❌ Port duplication → 无 (8011 唯一 Backend)
❌ Backend startup duplication → 无 (desktop 经 factory-runtime CLI)
❌ Client-specific business logic → 无
❌ UI import backend implementation → 无 (零 import Python)
✅ mock/ 生产零引用
```

## 五、关键边界确认

1. **Desktop 不启动第二 Backend**: 经 `factory-runtime start` 管理共享 8011 (main.rs:56)
2. **SSE 边界正确**: runtimeClient.subscribeEvents (EventSource 封装), 无 Web-specific semantics
3. **State 轻量**: AppState (轻量) + ConversationContext (会话), 无第二套 Production State
4. **共享层缺失**: 无 packages/shared — 当前单 Client 不需要

## 六、未来 Mobile 可行性

```
Production Core (8011)
      ↓ API Contract
  ┌────┼────┐
 Web  Desktop  Mobile (未来)
```

**✅ 允许**: API Contract 已统一 (client.ts 模式可复制), Production Core 不修改即可加 Mobile。

## 七、结论

**当前 Client 架构健康**: 无双事实/无重复/无强耦合/无第二 Backend。
唯一"不规范"是目录布局 (frontend 埋 console 下, desktop 独立根), 但**不影响生产**。
共享层 (ui/shared) 在单 Client 阶段无必要, 多 Client (Mobile) 时再抽。
