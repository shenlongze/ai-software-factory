# S30-ARCH — UI Topology Audit

> 日期: 2026-08-31 | 纯审计

## 当前 UI 全清单

| UI | 位置 | 技术 | 状态 |
|----|------|------|------|
| Web UI | factory-console/web/frontend/src/ | React 18 + TS + Vite | ✅ 主 UI |
| Desktop UI | desktop/ (Tauri 2) | Rust + WebView, 复用 web dist | ⚠️ 未构建 |
| Mobile | ❌ 不存在 | — | — |
| Shared Components | src/components/af/ (30+ 组件) | React | ✅ 单一 |
| API Client | src/api/client.ts | TS | ✅ 单一 (27 API) |

## 检查项

| 项 | 结果 |
|----|------|
| WebUI 散落? | ❌ 无 (唯一 frontend/) |
| Desktop 散落? | ❌ 无 (唯一 desktop/) |
| Mobile 散落? | — 不存在 |
| Shared component 重复? | ❌ 无 (components/af 单一) |
| API client 重复? | ❌ 无 (client.ts 单一) |
| UI 直接 import 后端模块? | ❌ 无 (零 import, 只走 API) |
| UI 有自己的 runtime/backend? | ❌ 无 |

## 结论

**UI 层本身健康**: 无散落、无重复 client、无强耦合。
**唯一问题**: WebUI 物理位置在 `factory-console/web/frontend/` (埋在后端目录下), 与 desktop 分离, 无统一 `ui/` 层。

## 建议

```
P1: 建 ui/web + ui/desktop (git mv, 修 static_dir/scripts 引用)
    保持 API client 单一, 未来 mobile 加 ui/mobile 复用同一 API
```
