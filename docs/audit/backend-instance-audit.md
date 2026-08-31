# S30-ARCH — Backend Instance Audit

> 日期: 2026-08-31 | 依据: 真实进程 + 代码

## 结论: 只有 1 个真实 API Backend

| 实例 | 端口 | 类型 | 是否 Backend | 证据 |
|------|------|------|-------------|------|
| factory start (uvicorn) | 8011 | **API Backend** | ✅ 是 | FastAPI, 全部业务端点 (313 个) |
| factory start (uvicorn) | 5180 | WebUI Static | ❌ 否 | 同一 app create_app(static_dir=dist) |
| vite dev | 5173 | UI Dev Server | ❌ 否 | node, 热更新 |
| service.py 常量 | 8099 | Preview URL | ❌ 未监听 | 未启动 |

## 追踪

```
8011 启动入口: factory start → cli_factory._start_backend → uvicorn base64
  Python module: factory_console.web.backend.fastapi_adapter
  App: create_app(factory_root=~/.factory)
  DB: factory.db (SQLite) + JSON stores (org/projects.json, console_sessions.json...)
  Session: console_sessions.json (sessions + messages)
  Conversation: conversation_os (rules) / sessions (LLM)
  Event: events.py + EventLogger (SQLite)
  Orchestrator: workforce.py (唯一)
```

## 任务→端口检查

```
扫描: 无 task→:8012 / agent→:8013 / project→:8014 模式
结论: 不存在 Backend duplication。执行是进程内库 (exec/), 不复制 API。
```

## 判断

- ✅ 正确: 8011 唯一 API, 5180 静态, 5173 dev, exec 进程内
- ⚠️ 待收敛: 5180 vs 5173 双 WebUI 入口 (P1)
- ⚠️ 双会话: sessions (LLM) vs conversations (规则) — 事实来源分裂 (P0)
