# Runtime Distribution — Local / Enterprise / Cloud 三种分发形态

> 日期: 2026-08-07 | 状态: 已确认 (15A-3c-3) | 前置: [runtime-service-model.md](./runtime-service-model.md) + [desktop-product-entry.md](./desktop-product-entry.md)
> 原则: Desktop 不是业务层 / Runtime Interface 是唯一替换边界 / 默认安全 / KISS
> 关联: phase15-runtime-design.md §1.6 / tauri.conf.json bundle.resources / main.rs `resolve_runtime_cmd_at`

## 1. 问题: Runtime 怎么交付到用户机器？

Desktop (Tauri Shell) 只是**入口层** — 真正的进程/状态/日志由 `factory-runtime`
CLI 提供。用户机器上没有 Python 3.12 环境、没有 factory-core 源码, 因此必须回答:
**runtime 二进制从哪来、怎么装、怎么替换**。本文定义三种分发形态, 以及让它们
可无缝替换的 Runtime Interface 契约。

```
┌────────────────────────────────────────────────┐
│ Desktop Shell (Tauri)                          │
│  resolve_runtime_cmd_at():                     │
│    0. (预留) DESKTOP_RUNTIME_REMOTE_ENDPOINT   │ ← Enterprise/Cloud 接入点
│    1. DESKTOP_RUNTIME_CMD (显式覆盖)           │
│    2. App 内嵌 bundle (Contents/Resources)     │ ← Local (当前)
│    3. PATH factory-runtime                     │
└────────────────────────────────────────────────┘
        │ 唯一控制面: factory-runtime CLI (Runtime Interface)
        ▼
   Local Embedded / Enterprise Remote / Cloud Service
```

## 2. Local Runtime (Desktop embedded) — 当前实现 (15A-3c-3)

**形态**: PyInstaller onedir (`dist/factory-runtime-bundle/`, ~38M), 通过
`tauri.conf.json` `bundle.resources` 整目录打进 App bundle:

```
AI Organization Factory.app/
  └── Contents/
      ├── MacOS/AI Organization Factory        (Tauri 主二进制)
      └── Resources/factory-runtime-bundle/
          ├── factory-runtime-bundle           (PyInstaller 入口, Mach-O arm64)
          └── _internal/                       (内嵌 Python 3.12 + 全部依赖)
              ├── Python.framework / python3.12
              ├── console_web/  (Console 前端静态资源)
              └── ... (fastapi/uvicorn/pydantic/... dist-info)
```

关键性质 (验证见 §7):

- **无 Python 依赖**: `_internal/` 自带解释器, 主二进制 otool 仅链
  `libSystem/libz`; 用户机器不需要系统 python / node / git。
- **发现链**: env > embedded (App 内) > PATH (`resolve_runtime_cmd_at`),
  内嵌路径在打包后自动命中, dev 模式回退 PATH, 测试注入走 env。
- **数据隐私**: data_root 由 `factory-runtime init` 创建, 权限 **0700**;
  token 文件 **0600**; 日志三文件 `logs/{runtime,core,console}.log`。
- **未签名分发**: 无开发者证书 → 首次打开需右键→打开 (或
  `xattr -d com.apple.quarantine`); 不引入 codesign 依赖。
- **升级**: 重建 bundle + `tauri build --bundles app,dmg` → 新 dmg 整包替换。

## 3. Enterprise Runtime (remote/container) — 规划 (Phase 16+)

**形态**: runtime 部署在企业内网主机 / 容器, Desktop 通过远程 endpoint 驱动。

- 接入点已预留: `DESKTOP_RUNTIME_REMOTE_ENDPOINT`
  (`main.rs RUNTIME_REMOTE_ENDPOINT_ENV`, 解析链第 0 优先级)。
- Desktop 侧改动仅限 `resolve_runtime_cmd_at` 增加 remote 探测
  (HTTP 健康 + endpoint 状态), **不新增业务逻辑**; Bridge 的
  start/stop/status 语义映射为远程 API 调用。
- 适用: 多用户共享部署 / 集中管控 / 数据不出内网。

## 4. Cloud Runtime (service) — 规划 (Phase 16+)

**形态**: 托管 SaaS 服务, Desktop 变成纯前端壳 (或 Web 入口)。

- 同一 remote 接入点扩展: endpoint 指向云服务; 身份/租户鉴权在
  Bridge 层之前处理 (shell 不存业务凭据 — 仅传 endpoint + 会话)。
- 适用: 零安装 / 跨设备 / 团队协作场景。

## 5. Runtime Interface — 可替换性的唯一边界

三种形态共享同一契约, 替换 runtime 形态**不触碰 Desktop 业务逻辑**:

```text
factory-runtime --root <root> init    → 7 子目录 + token + 状态文件 (rc 0)
factory-runtime --root <root> start --json  → 状态 JSON (含 port, ready)
factory-runtime --root <root> stop  --json  → 状态 JSON (幂等)
factory-runtime --root <root> status --json → 状态 JSON
factory-runtime --root <root> restart --json→ 状态 JSON
logs 由 Desktop 直接 tail <root>/logs/{runtime,core,console}.log
```

状态 JSON 字段 (RuntimeStatus): status / pid / port / version /
started_at / stopped_at / core_alive / console_alive / core_exit_code /
console_exit_code。替换约束:

1. **命令形态不变** — Local=子进程, Enterprise=远程代理转发同形命令,
   Cloud=服务端同形 API; Desktop 的 Bridge 只认命令形态。
2. **状态语义不变** — `starting/ready/stopping/stopped/failed/idle`
   对齐 `runtime/state.py RUNNING_STATUSES`。
3. **日志契约不变** — 三文件位置与内容形态是 health_detail 的输入。
4. **失败可替换** — 远程不可达 → BridgeError → 用户语言错误, 与
   Local runtime 缺失同路径 (friendly_error), 用户侧体验一致。

## 6. 构建与分发命令 (Local)

```bash
# 1) 构建 runtime bundle (PyInstaller onedir, 含冒烟)
scripts/build-runtime-bundle.sh            # → dist/factory-runtime-bundle/

# 2) 打包 dmg (release 编译 + .app + dmg; resources 自动内嵌 bundle)
cd desktop/src-tauri && npx tauri build --bundles app,dmg
# 产物:
#   target/release/bundle/dmg/AI Organization Factory_<ver>_<arch>.dmg
#   target/release/bundle/macos/AI Organization Factory.app

# 3) 用户安装: 打开 dmg → 拖入 Applications; 未签名首次打开
#    右键 → 打开 (或 xattr -d com.apple.quarantine "<path>")
```

## 7. 验证 (15A-3c-3 实测记录)

| 项 | 结果 |
|---|---|
| dmg | 25M, `AI Organization Factory_0.1.0_aarch64.dmg` |
| .app 结构 | `Contents/MacOS` 主二进制 + `Resources/factory-runtime-bundle/` (onedir 整目录) |
| 内嵌 runtime 冒烟 | 从 App Resources 内 bundle `init/start/stop`: 7 子目录 + 0700 + Console READY + /api/dashboard 200 |
| Fresh machine 模拟 | PATH 无 python/node/git + 空 HOME 数据目录: 启动 → data_root 0700 → READY → 三日志 → graceful stop, 零残留 |
| 发现优先级 | env > embedded (App 内) > PATH (单测 + 集成测试覆盖) |
| 无 runtime | 友好用户语言错误 (无技术词) |
| 测试 | cargo 116+ / pytest 4241+ 全绿; Core/Console diff = 0 |

## 8. 已知限制

- **未签名/未公证**: Gatekeeper 首次拦截, 需右键打开; 正式分发需
  Developer ID + notarization (本阶段明确不引入 codesign)。
- **单架构**: 当前产物 arm64 (本机构建); 通用分发需 x86_64 构建或
  universal2 合并 (后续阶段)。
- **整包升级**: Local embedded 无增量更新通道 (dmg 全量替换)。
- **Remote/Cloud 未实现**: 仅预留 env 接入点与契约, 无代码路径。
