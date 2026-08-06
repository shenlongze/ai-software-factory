# desktop/ — Desktop Shell (Tauri 2)

AI Software Factory 桌面壳。**永远不是业务层** — 只做 WebView Host,
Runtime 唯一控制入口是 `factory-runtime` CLI (经 `src/runtime.rs` bridge)。

```
desktop/
├── src-tauri/
│   ├── Cargo.toml         Tauri 2.x 最小依赖
│   ├── tauri.conf.json    app 名 / 窗口 / frontendDist
│   ├── capabilities/      最小权限 (core:default)
│   └── src/
│       ├── main.rs        入口: Builder + invoke_handler + 最小 lifecycle
│       └── runtime.rs     runtime bridge: start/stop/status/logs (经 factory-runtime CLI)
├── ui/                    前端 dist 挂载 (symlink → factory-console/web/frontend/dist, 不重开发)
└── packaging/             占位 (Phase 15A-3c 打包用)
```

## 架构约束 (用户强制)
1. Desktop 永远不是业务层 (禁 Agent/Organization/Workflow/Task/Decision 逻辑)
2. Runtime 唯一控制: Rust 禁止直接 spawn factory CLI / uvicorn —
   唯一入口 `factory-runtime` CLI 子进程 (env `DESKTOP_RUNTIME_CMD` 可覆盖, 测试注入 fake)
3. 不绑定 Developer UI — 只做 WebView Host (未来 CEO/Manager/Operation/Approval/Audit 扩展)
4. runtime bridge 最小: start/stop/status/logs, 无 business command
5. 数据目录保持 `<data_root>` (默认 macOS: ~/Library/Application Support/ai-software-factory,
   env `DESKTOP_DATA_ROOT` 覆盖); 状态全部由 factory-runtime 管理
6. 打包 (dmg) 属 Phase 15A-3c; Python 捆绑属 15A-3d — 本阶段不复杂化

## 开发
```bash
brew install rust            # 一次性
cd desktop && npm i          # @tauri-apps/cli (仅 tauri dev/build 需要)
cd src-tauri && cargo build  # 编译
cargo test                   # bridge 单测 + 集成 (fake runtime)
```
