# 01 — CURRENT STRUCTURE (2026-09-06, READ-ONLY)

## 顶层地图 (真实)
- 单一 Python 发行版 (pyproject.toml package-dir 拼接):
  factory-core/ (域/理解/workflow/workspace 等命名空间包)
  factory-console/ (~70 模块: domain truth + services + runtime + CLI + web/)
  factory-exec/ → import 名 exec (agent runtime: Architect/Developer/Tester/
    ReleaseAgent/AgentRuntime)
  factory-org/ → import 名 org (Project/Workflow lifecycle M3 域)
- factory-runtime/ (独立 pyproject; runtime.cli 启动/停止后端 — desktop 依赖)
- desktop/ (Tauri 2 壳: src-tauri/ Rust [main/launcher/runtime], src/ui/
  原生 launcher, ui/ = frontend build 副本, packaging/)
- bin/factory (CLI 薄包装)
- 数据/残留: workspace/ projects/ examples/ (项目/示例数据);
  $SMOKE_ROOT/ + exec/checkpoints.json (运行时误放残留); build/ dist/
  (构建产物)

## 入口 → 后端 → 域 关系 (真实)
WebUI  React(factory-console/web/frontend) --fetch--> fastapi_adapter(374
  路由, 同进程服务 API+静态 dist) --> ConsoleService/domain services -->
  canonical stores (~/.factory)
Desktop Tauri(main.rs) --Command::new--> factory-runtime CLI --> uvicorn
  (禁直 spawn Core/uvicorn — 代码注释); launcher UI 内嵌
CLI     bin/factory --> factory_console.cli_factory.main --> console services
API     374 路由 (projects/sessions/tasks/artifacts/acceptance/learning...)

## 依赖方向 (真实)
desktop --factory-runtime--> backend (子进程+HTTP)
frontend --HTTP--> backend
cli_factory --import--> console 模块
backend --import--> console domain/service 模块 (同包)

## factory-console/web/frontend 内部
src/{api client.ts 700 行 / components/ af UI + ds 设计系统 / pages 12 /
     state AppState+workspace (UI state) / models types+domain (72 type,
     纯投影) / mock (projects/runtime/workspace — 仅测试+诚实 fallback) /
     hooks / utils / design}
→ 无业务真相: 全经 api/client.ts fetch; mock 诚实标 is_mock=true
