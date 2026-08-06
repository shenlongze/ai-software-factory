# Runtime Service Model — Service vs Command (架构裁决 B)

> 日期: 2026-08-07 | 状态: 已确认 (架构裁决 B, 15A-3c) | 前置: Phase 15A-3b (8abce8c)
> 原则: Core 零修改 / Extension 化 / KISS / 默认安全
> 关联: phase15-runtime-design.md §1.6 (已同步) / factory-runtime (manager/watchdog/health/cli)

## 1. 问题: Runtime 该"常驻"什么？

Phase 15A-3 早期设计把 Core 当作 daemon 管理 (RuntimeManager 单父进程下
Core CLI 子进程常驻 + watchdog 看护)。评审发现该模型三个问题:

1. **Core 是命令界面 (CLI), 不是服务** — `factory <command>` 每次调用即
   起即退, 常驻只是"挂着一个 idle 进程", 无业务价值, 只有进程管理开销。
2. **watchdog 误报** — Core 命令退出是常态 (命令执行完就退出), 若把退出
   当 crash 处理, watchdog 会无限重启空进程 / 误置 failed。
3. **跨进程状态失真** — CLI `status` 是新进程, 靠 core.pid 判断 Core
   存活, 而 Core 根本没有常驻进程可判。

**裁决 B: 引入 Service vs Command 双模型。** 只把真正长期运行的组件
(managed services) 当服务管理; Core 降级为"命令执行器" (command
executor), 每次调用即起即退, 退出是预期。

## 2. 双模型定义

```
factory-runtime
  ├── Managed Services    (常驻, 服务契约: 进程存活 [+ HTTP 探针])
  │     └── console       (uvicorn + fastapi_adapter, 127.0.0.1 回环)
  │                       当前唯一; 未来: Agent Worker / Scheduler
  └── Command Execution   (短生命周期, 命令契约: 调用 → 退出码/stdout/stderr)
        └── core          (factory CLI; health = 命令可用性, `--help` rc 0)
```

| 维度 | Managed Service (Console) | Command (Core) |
|:-----|:--------------------------|:---------------|
| 生命周期 | 常驻 (runtime 生命周期绑定) | 每次调用即起即退 |
| 健康 | 进程存活 + HTTP /api/dashboard 200 | 命令可用性 (`--help` rc 0) |
| 退出 | 非预期 → watchdog 重启 (≤3 次, 超限 failed) | **预期**, 不重启不报警 |
| 进程引用 | Popen 持有 + console.pid 文件 | 无 (不写 core.pid) |
| 状态键 | console_alive / console_healthy / service_health | core_available / core_alive / command_health |
| 持久化 | console.pid (进程) | core.cmd (命令 argv, 替代 core.pid) |
| 未来扩展 | Agent Worker / Scheduler 注册 managed_services | 任意短命令, 无需注册 |

## 3. 为什么 Core 不需要 daemon？

1. **命令即界面**: Core 的全部能力经 `factory <command>` CLI 暴露
   (Phase 1-14B 已验证)。每次调用 = 一次子进程, 进程隔离天然成立
   (Runtime 崩溃不影响 Core 数据; 命令失败不传染 runtime 状态)。
2. **零常驻收益**: 常驻 Core 不提供任何命令之外的增量能力; 反而引入
   崩溃判定、重启策略、端口/pid 管理等一整套复杂度。
3. **失败语义清晰**: 命令失败 (rc ≠ 0) 是**业务结果**, 不是**系统故障**。
   runtime 的职责是执行并返回结果, 不是"保证命令永不失败"。
4. **watchdog 简化**: 只 watch managed services (当前 Console 一个),
   Core 退出不再进入重启/置 failed 路径, 误报面归零。
5. **启动提速**: start 只依赖 Console 健康, 不等待 Core; Core 命令
   不可用 (如 bundle 收集缺失) ≠ 启动失败, 状态如实报告 available=False。

## 4. 跨进程命令持久化: core.cmd

CLI `status` / `stop` / `run_command` 由新进程执行, 无原 RuntimeManager
实例的 factory_cmd 配置。旧模型用 core.pid 传递"Core 进程", 新模型无
Core 进程可传 — **改传"Core 命令"**:

```
start() → 解析 Core 命令 argv → 原子写 config/core.cmd (600, JSON {"cmd": [...]})
status()/run_command() (新进程, 默认 factory_cmd) →
    读 core.cmd → 用同一命令做可用性检查 / 执行
    文件缺失/损坏 → 失败安全回落 bundle __core 路由 / "factory"
```

- core.cmd 是**配置属性**: stop 不删除 (命令可用性独立于 runtime 运行态)。
- core.pid 不再写入 — 测试与实现同步移除该断言。
- bundle (PyInstaller frozen) 下解析结果为 `[sys.executable, "__core"]`,
  跨进程 status 同样经 core.cmd 可见, 无需进程引用。

## 5. Runtime 如何管理未来 Agent / Scheduler (Phase 16+)

未来组件分两类, 分别落位:

**常驻服务** (Agent Worker / Scheduler / 未来任何长生命周期 worker):
- 在 `RuntimeManager.managed_services` 注册服务名;
- 提供 `service_proc(name)` 进程引用 + `restart_process(name)` 重启路径;
- watchdog 循环与 ServiceHealth 契约**零改动自动覆盖** (按
  managed_services 轮询);
- 每个服务按需叠加探针 (端口/心跳), health.py 的
  `service_health(name, proc, base_url)` 已支持。

**短命令** (Phase 17 AI Professional 的任意工具调用):
- 直接经 `run_command(args)` 执行, 无需注册;
- 命令失败以 returncode 表达, 不污染 runtime 状态。

## 6. 状态 JSON 契约 (Desktop runtime.rs 兼容)

```json
{
  "status": "ready",
  "core_alive": true,          // = command availability (兼容键)
  "console_alive": true,
  "core_exit_code": null,      // Core 非 daemon, 恒 null
  "console_exit_code": null,
  "core_available": true,      // 语义键: Core 命令可用性
  "console_healthy": true,     // 语义键: Console service 健康
  "service_health": {"name": "console", "alive": true, ...},
  "command_health": {"name": "core", "available": true, ...}
}
```

## 7. 影响与边界

- **实现**: factory-runtime/runtime/{manager,health,watchdog,cli}.py
  (15A-3c 已落盘); core.cmd 持久化 (15A-3c-2)。
- **测试**: 125+ passed (15A-3c-2 全绿 ≥4241); Core 非 daemon 断言
  (core_proc 恒 None / 无 core.pid / 命令退出 watchdog 零重启)。
- **Desktop**: 状态解析只读 core_alive/console_alive/exit codes — 契约
  未破坏; runtime.rs 无需改动 (git diff desktop = 0 验证)。
- **Phase 17 扩展路径**: Agent = managed service (常驻 worker) 或
  command (一次性任务), 按 §5 落位; 不推翻本模型。
