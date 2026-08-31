# S30-ARCH — Port Registry

> 日期: 2026-08-31 | 依据: 真实监听 (lsof) + 代码定义 (grep)

| Port | Service | Owner | Purpose | 环境 | 启动方式 | 状态 |
|------|---------|-------|---------|------|---------|------|
| **8011** | AI Factory Backend | factory start | 全部业务 API (FastAPI) | 生产/开发 | `factory start` | ✅ 受管 |
| **5180** | WebUI Static | factory start | serve frontend/dist (静态) | 生产/开发 | `factory start` | ✅ 受管 |
| **5173** | WebUI Dev Server | 手动 | vite dev (热更新) | 开发 | `npm run dev` | ⚠️ 与 5180 并存 |
| **8099** | Runtime Preview | service.py | preview URL 常量 | 定义 | — (未监听) | ⚠️ 未监听 |

## Orphan Port 检查

- 8011: 有 owner (factory start) ✅
- 5180: 有 owner (factory start) ✅
- 5173: 有 owner (手动 vite) ⚠️ 但与 5180 职责重叠 — **P1: 需收敛 (二选一)**
- 8099: 定义未监听 — **P2: 确认用途或移除**

## 收敛建议

```
开发: factory start → 8011 + 5180 (标准)
     或 npm run dev → 5173 (仅前端开发, 需代理 /api → 8011)
生产: 8011 + 静态 assets (同一 uvicorn serve, 5180 合并)
```
