# S30-ARCH — Repository Topology & Target Architecture

> 日期: 2026-08-31 | 纯审计 + 目标结构 (不执行)

---

## 一、当前 Repository Topology

```
ai-software-factory/
├── factory-console/        ← ⚠️ 职责混合: 后端 (264 py) + WebUI (259 ts) + API (web/backend)
├── factory-core/           ← 核心域 (138 py)
├── factory-exec/           ← 执行器 (52 py)
├── factory-org/            ← 组织 (18 py)
├── factory-runtime/        ← Runtime (12 py)
├── factory_console/        ← ⚠️ 打包别名壳 (2 py, 与 factory-console 双包名)
├── desktop/                ← Tauri 壳 (独立)
├── build/  dist/           ← ⚠️ 构建副本
├── tests/  docs/  scripts/
```

## 二、UI 拓扑 (当前)

| UI | 位置 | 状态 |
|----|------|------|
| Web UI | factory-console/web/frontend/ | ✅ 唯一 WebUI |
| Desktop | desktop/ | ✅ 独立壳, 复用 web dist |
| Mobile | ❌ 不存在 | — |
| Shared Components | components/af/ | ✅ 单一 |
| API Client | src/api/client.ts | ✅ 单一, 无重复 |
| UI→Backend 耦合 | 零 import 后端模块 | ✅ 只走 API |

**UI 无散落, 无重复 API client, 无强耦合。唯一问题: WebUI 埋在 factory-console/ 下。**

## 三、目标 Repository Topology (建议)

```
ai-software-factory/
├── ui/                       ← 统一 UI 层 (新)
│   ├── web/                  ← WebUI (从 factory-console/web/frontend 迁入)
│   ├── desktop/              ← 桌面壳 (从 desktop 迁入)
│   └── mobile/               ← 未来
├── backend/                  ← 统一 Backend (从 factory-console 业务代码迁入)
│   ├── api/                  ← fastapi_adapter
│   ├── application/          ← 应用服务
│   └── runtime_integration/
├── core/                     ← 生产核心 (factory-core 保留)
├── exec/  org/  runtime/     ← 执行/组织/运行时 (保留)
├── packages/                 ← 共享 (api client, contracts) — 若多端需要
├── tests/  docs/  scripts/
└── pyproject.toml
```

**为什么**: 职责分层 — UI (客户端) / Backend (API+应用) / Core (域) / Runtime (执行) 边界清晰, Web/Desktop/Mobile 是同一 Backend 的不同客户端。

## 四、迁移步骤 (P0/P1/P2)

### P0 (前置 — 解决事实来源)
```
P0-1 统一会话事实来源: sessions (LLM) 为 WebUI Runtime, conversations 降级/对齐
P0-2 统一 Intent: LLM 检测为主, 规则 fallback
```

### P1 (目录收敛)
```
P1-1 建 ui/ 目录: git mv frontend → ui/web, desktop → ui/desktop
P1-2 修引用: static_dir/scripts/vite 路径
P1-3 收敛双 WebUI 入口: 5180 vs 5173 二选一
P1-4 factory_console 双包名: 清理别名壳
```

### P2 (深度重构)
```
P2-1 后端分层: factory-console 平铺 68 模块 → backend/application/domain
P2-2 生命周期阶段模块化: Discovery/Market/UX 从字符串 → 模块
P2-3 构建副本治理: build/dist 同步机制
```

## 五、最终回答 (任务要求 14 问)

1. **当前几个 Backend?** → 1 个 (8011)
2. **为什么多端口?** → 8011 API + 5180 静态 + 5173 dev (非 duplication)
3. **合理 Worker?** → 无独立 worker 端口 (exec 是进程内库)
4. **Backend duplication?** → 无
5. **Web/Desktop/Mobile 在哪?** → web=frontend/, desktop=desktop/, mobile=无
6. **如何组织?** → ui/web + ui/desktop, 共享 8011
7. **重复 API/Runtime/Session?** → Session 双事实 (P0-1), 无重复 API/Runtime
8. **多 Orchestrator?** → 无 (workforce.py 唯一)
9. **共享 Backend?** → ✅ 完全可以 (Web/Desktop/Mobile 都是 8011 客户端)
10. **迁移步骤?** → P0(2步) + P1(4步) + P2(3步) ≈ 9 步

## 六、结论

**当前架构无 Backend duplication / 多 Orchestrator / UI 强耦合 — 核心健康。**
主要债务: ①会话双事实 ②UI 埋在 console ③双 WebUI 入口 ④双包名。
**建议先 P0 (会话统一), 再做 P1 (ui/ 目录收敛), P2 暂缓。**
