# Desktop Product Entry — AI Organization Factory 入口 (Phase 15A-3b)

> 日期: 2026-08-07 | 状态: 已实现 (15A-3a 桥 + 15A-3b 入口 UI)
> 前置: [phase15-runtime-design.md](./phase15-runtime-design.md) + Phase 15A-3a (5a3fc0f)
> 原则: Desktop 不是业务系统 / 不保存业务数据 / 错误用用户语言 / 零 Core·Console·Runtime 修改

## 1. 定位: Desktop 是什么, 不是什么

**Desktop = AI Organization Factory Application Entry (应用入口层)。**

```
┌──────────────────────────────────────────────────┐
│ Desktop Shell (Tauri, 本模块)                     │
│  ├── Launcher UI (src/ui, 原生 JS 内嵌)          │  ← 本文件描述
│  │    ├── Factory Header                         │
│  │    ├── Workspace Area (预留占位, 不实现业务)    │
│  │    └── System Status (底层状态, 非首页唯一内容) │
│  └── Bridge (runtime_* / health_detail /         │
│       open_console — 无任何 business command)     │
├──────────────────────────────────────────────────┤
│ factory-runtime (唯一控制面, 进程/状态/日志)       │
├──────────────────────────────────────────────────┤
│ Organization / Intelligence / Extension 层        │
│ (Phase 16+: 公司/部门/员工/审批/知识 — 未来提供)    │
└──────────────────────────────────────────────────┘
```

### 为什么 Desktop 不是业务系统

1. **业务由未来层提供** — AI 公司的创建、部门管理、员工雇佣/分配/考核
   (Organization), 规划智能 (Planning Intelligence), 行业模板 (Extension)
   均属 Phase 16+, 由 Runtime 之上的 Organization/Intelligence/Extension 层
   提供。Desktop 若提前实现业务, 会与未来架构重复并破坏分层。
2. **最小攻击面** — 壳只做「启动/停止/状态/日志 + 导航」, 不触碰任何业务写路径;
   未来公司隔离 (多公司数据分区) 由 Runtime/Organization Layer 管理,
   Desktop 天然支持 (只读状态, 无业务数据)。
3. **可替换性** — 入口层极薄, 未来若换 UI 技术栈 (如 React Console 化),
   Bridge 不变, 业务层不受影响。

### 明确的边界 (用户强制)

| 维度 | Desktop 做 | Desktop 不做 |
|:-----|:-----------|:-------------|
| 业务命令 | 无 (禁 create_agent/create_project/assign_task) | Phase 16+ 经 Organization Layer |
| 数据 | 不保存 Company/Agent/Knowledge 数据 | 全部在 `<data_root>`, Runtime 管理 |
| 状态 | 只读展示 (数据源 = factory-runtime CLI) | 不维护自身状态副本 |
| 日志 | 查看 (Troubleshooting 定位) | 日志分析属未来 Analysis Agent |
| 恢复 | System Recovery (restart runtime) | 非用户日常操作流程 |

## 2. UI 结构 (预留)

```
Factory Header ── AI Organization Factory 品牌 + 状态徽章 (READY/STARTING/FAILED/STOPPED) + 版本
├── Workspace Area ── 占位: "Workspace 即将上线"
│     (预留 CEO / Manager / Employee / Approval / Knowledge 模块)
├── System Status ── Runtime 状态 + uptime + Console Port + Version
│     ├── 首次启动流程: Initializing Factory… → start → READY → [打开 Factory Console]
│     ├── Health view: Runtime ✓ / Core ✓ / Console ✓ (+ reason + suggestion + Retry)
│     │     (预留 Organization/Agents/Knowledge/Learning — 未来项, 只占位)
│     └── 错误: "Factory startup failed: <原因摘要>" + [重试] (用户语言)
├── System Recovery ── FAILED/STOPPED 时出现, [Restart Runtime] (stop+start)
└── Log Viewer ── 3 tab (runtime.log/core.log/console.log), 200 行, 刷新
      (Troubleshooting 定位, 非用户主要功能)
```

技术: 原生 HTML/CSS/JS, 无框架 (KISS), 经 `frontendDist: ../src/ui` 内嵌
Tauri 资源; `withGlobalTauri` 暴露 `window.__TAURI__.core.invoke`。
状态轮询: `setInterval` 2s → `runtime_status` + `health_detail`。

## 3. Bridge 契约 (新增仅 runtime_restart + health_detail)

| command | 输入 | 输出 | 说明 |
|:--------|:-----|:-----|:-----|
| `runtime_start` | — | RuntimeStatus JSON | 首次启动 (CLI start --json) |
| `runtime_stop` | — | RuntimeStatus JSON | 幂等 |
| `runtime_status` | — | RuntimeStatus JSON | 轮询数据源 |
| `runtime_logs` | lines | LogBundle JSON | 3 文件 tail |
| `runtime_restart` | — | RuntimeStatus JSON | **stop + start 组合** (Recovery) |
| `health_detail` | — | HealthDetail JSON | **Runtime/Core/Console 组件 + uptime/version/port + 用户语言 reason/suggestion** |
| `open_console` | port | — | 纯 UI 导航 (打开 http://127.0.0.1:port) |

全部命令从 `AppState.data_root` 取路径 (JS 不传路径);
错误统一经 `launcher::friendly_error` 转用户语言 — **禁暴露
Python/Rust/uvicorn/subprocess/exit code/路径**。

## 4. 首次启动 / 错误 / 恢复流程

```
首次启动:  用户打开 App → launcher 加载 → status 检查 (idle)
           → "Initializing Factory…" → runtime_start → READY
           → [打开 Factory Console] → 新窗口加载 http://127.0.0.1:<port>
失败:      "Factory startup failed: <原因摘要>" + [重试]
           (原因摘要用户语言; 详细技术信息只进 runtime.log)
崩溃/停止: System Recovery 区出现 → [Restart Runtime] → stop+start → READY
关闭:      launcher 窗口关闭 → graceful stop (SIGTERM 语义在 factory-runtime)
           → 无残留进程 → 退出; console 窗口关闭 → 仅关窗, runtime 保持
```

## 5. 未来企业隔离 (Phase 16+ 预留)

- 公司隔离经 Runtime/Organization Layer: `<data_root>` 下按公司/部门分区,
  Desktop 只读状态, 天然支持多公司切换 (状态 JSON 不变)。
- Workspace 占位即未来业务入口: CEO/Manager/Employee/Approval/Knowledge
  模块将加载到 Workspace Area, 不改变 Bridge 边界。
- Log 分析: 未来 Analysis Agent 消费 `<data_root>/logs/*`, Desktop 日志
  Viewer 保持 Troubleshooting 定位。

## 6. 验证

- `cd desktop/src-tauri && cargo test` — 98 全绿 (59 既有 + 39 新增:
  restart/health_detail/uptime/friendly_error/UI 资源断言/产品级 Fresh Launch·
  Failure Recovery·Shutdown)
- `cargo build` — 成功 (launcher 资源内嵌)
- 产品级冒烟: fake runtime 注入 launcher 流程 (launch→ready→logs→restart)
- 回归: pytest 4217 全绿; `git diff factory-core/ factory-console/ factory-runtime/` = 0
