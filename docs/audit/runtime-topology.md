# S30-ARCH — Repository & Runtime Topology Audit

> 日期: 2026-08-31 | 方法: 纯审计 (零修改) | 依据: 真实代码 + 真实进程

---

## 一、Repository 拓扑 (当前真实)

```
ai-software-factory/
├── factory-console/       ← 主代码: 后端 + WebUI (264 py + 259 ts)
│   ├── web/backend/       ← FastAPI Adapter (8011 API)
│   └── web/frontend/      ← WebUI (React) + dist
├── factory-core/          ← 核心域 (138 py): events/execution/intelligence/metrics...
├── factory-exec/          ← 执行器 (52 py): exec/
├── factory-org/           ← 组织 (18 py): org/
├── factory-runtime/       ← Runtime (12 py)
├── factory_console/       ← 打包别名壳 (2 py, import 胶水)
├── desktop/               ← Tauri 桌面壳 (独立 package.json)
├── build/                 ← 构建产物 (433 py 副本)
├── dist/                  ← 打包 bundle
├── tests/                 ← 测试 (665 py)
├── docs/  scripts/  demo/  examples/  unused/
```

## 二、Runtime 拓扑 (当前真实, 3 监听 + 1 定义)

| 端口 | 进程 | PID | 启动方式 | 职责 |
|------|------|-----|---------|------|
| **8011** | Python uvicorn | 30608 | factory start (base64 bootstrap) | **API Backend** (FastAPI, 全部业务端点) |
| **5180** | Python uvicorn | 30333 | factory start | **WebUI 静态服务** (serve dist) |
| **5173** | node vite | 43251 | 手动 npm dev | **WebUI Dev Server** (vite, 手动启动) |
| **8099** | (定义) | — | service.py:2372 | Runtime Preview URL (未监听) |

**注意**: 5173 (vite dev) 和 5180 (静态服务) **同时存在** — 两个 WebUI 入口!
- 5173 = 开发者手动启动的 vite (热更新)
- 5180 = factory start 的静态 dist 服务

## 三、Backend 实例数

**结论: 只有一个真实 API Backend (8011)。**
- 5180 = 同一 uvicorn 应用的第二个实例, 只 serve 静态文件
- 5173 = vite dev server (不是 backend)
- 8099 = 未监听的 URL 常量

**没有 Backend duplication。** 任务→端口的模式不存在 (无 8012/8013/8014)。

## 四、职责分类

| 目录 | 职责 | 谁依赖 | 谁启动 | 重复? | 越界? |
|------|------|--------|--------|-------|-------|
| factory-console | 后端+WebUI | 全部 | factory start | ⚠️ 混合 (后端+前端同目录) | 🔴 UI 埋在 console 下 |
| factory-core | 核心域 | console/exec | 无 (库) | ❌ | ❌ |
| factory-exec | 执行器 | console | 无 | ❌ | ❌ |
| factory-org | 组织 | console | 无 | ❌ | ❌ |
| desktop | 桌面壳 | web dist | tauri dev | ❌ | ❌ |
| factory_console | 打包胶水 | pyproject | pip | ⚠️ 与 factory-console 双包名 | 🔴 |
| build/dist | 构建产物 | 部署 | build 脚本 | ⚠️ 副本 | ❌ |

## 五、启动方式审计

```
factory start → 8011 (API) + 5180 (静态 WebUI)  ← 标准
npm dev       → 5173 (vite)                      ← 手动, 开发者用
tauri dev     → desktop                          ← 未构建
```

**用户运行 AI Factory 只需 `factory start` (1 个命令起 2 个端口)。不必要多启动。**
5173 是开发者手动起的 vite, 与 5180 并存 — 需要收敛 (二选一)。

## 六、目标 Runtime 拓扑

```
Development:
  factory start → Backend :8011 + WebUI static :5180 (或 vite :5173 二选一)
  WebUI :5173/5180 → API :8011
  Desktop (tauri) → API :8011
  Mobile (未来)   → API :8011

Production:
  AI Factory Backend :8011 + WebUI static assets (同进程 serve)
```

**核心原则: 一个 Backend (8011), UI Dev Server 可独立, 无 Backend duplication。**
