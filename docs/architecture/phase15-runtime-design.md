# Phase 15 Architecture Design — Product Runtime & Desktop Edition

> 日期: 2026-08-07 | 状态: 架构评审, 待确认
> 前置: Phase 1-14B + Roadmap 15-21 (5195385)
> 原则: Core 零修改 / Extension 化 / 安全·可控·透明·可扩展 / 默认安全

## 1. factory-runtime 架构设计

### 1.1 Runtime 是否独立 Python Package？

**是。** factory-runtime 独立 Extension（独立目录 + 独立安装单元），但**不 import Core 内部**：

```
factory-runtime/
├── pyproject.toml       独立包 (name=factory-runtime)
├── runtime/
│   ├── manager.py       RuntimeManager (进程生命周期)
│   ├── launcher.py      Core CLI / Console 启动器
│   ├── config.py        配置加载 (默认→用户→项目 三层合并)
│   ├── datadir.py       数据目录管理 (平台规范路径 + 迁移)
│   ├── logging.py       日志管理 (轮转/级别/独立文件)
│   └── health.py        健康检查 (Console /api/dashboard)
└── tests/               独立测试空间
```

安装形态：pip 包（开发）+ PyInstaller 捆绑（Desktop 分发）。

### 1.2 与 Core 的通信方式？

**子进程隔离（推荐），不 import Core 内部：**

```
RuntimeManager → subprocess → factory CLI (已有 console script)
  - 启动: factory --root <data> <command>
  - 停止: SIGTERM (graceful) → SIGKILL (超时兜底)
  - 状态: 退出码 + 事件日志
```

理由：
- 进程隔离：Runtime 崩溃不影响 Core 运行；Core 崩溃可 watchdog 重启
- 可暂停/可恢复：进程级（checkpoint 语义已有，Runtime 管进程）
- 零 Core import → 冻结铁律天然满足（Runtime 只调 CLI 边界）
- 未来 17 Real Execution 的 sandbox 同模式

### 1.3 与 Console 的通信方式？

```
RuntimeManager → subprocess → uvicorn (factory-console fastapi_adapter)
  - 启动: uvicorn --port <随机或固定> --host 127.0.0.1
  - 健康: GET /api/dashboard → 200
  - 停止: SIGTERM graceful
```

Desktop 内嵌 Console：Tauri WebView 加载 http://127.0.0.1:<port>（本地回环）。

### 1.4 数据目录标准？

**用户级主目录（Desktop 模式）+ 项目级并存（CLI 模式）：**

```
macOS:   ~/Library/Application Support/ai-software-factory/
Linux:   ~/.config/ai-software-factory/ + ~/.local/share/ai-software-factory/
Windows: %APPDATA%\ai-software-factory\
```

统一抽象 runtime 数据根（跨平台映射），内部结构：

```
<data_root>/
├── config/       config.yaml (用户配置)
├── providers/    providers 配置 (Phase 16)
├── agents/       agents 配置 (Phase 16)
├── skills/       skills 配置 (Phase 16)
├── mcp/          MCP 配置 (Phase 16)
├── logs/         日志 (轮转)
└── data/         工厂数据 (.factory 结构: tasks/events/intelligence/...)
```

### 1.5 Windows/macOS/Linux 差异处理？

| 维度 | 处理 |
|:-----|:-----|
| 路径 | platformdirs 风格映射（1.4 表） |
| 进程信号 | POSIX SIGTERM; Windows 用 proc.terminate() + taskkill 兜底 |
| 打包 | dmg (macOS) / msi (Windows) / deb+AppImage (Linux) — Tauri 原生 |
| 路径权限 | 数据目录 700/750 (POSIX); Windows ACL 默认 |
| 换行/编码 | 全 UTF-8, 统一 config 解析 |

### 1.6 进程管理方案？

```
RuntimeManager (单父进程):
  ├── Core CLI 子进程 (factory daemon/命令)
  └── Console 子进程 (uvicorn)

- 启动: 顺序 (Core → Console), 健康检查通过才报 READY
- 停止: 逆序 graceful (Console → Core), 超时强杀
- 崩溃: watchdog 检测退出码 → 自动重启 (最多 N 次, 记录)
- 状态: runtime status → JSON (pid/uptime/health/log tail)
- 日志: 各自独立文件 + 统一事件
```

## 2. Desktop Shell 技术评估

| 维度 | Tauri (推荐) | Electron |
|:-----|:-------------|:---------|
| 安全性 | Rust 内存安全 + 最小攻击面 + 无 Node 运行时 | Node 运行时 + 大攻击面 |
| 包大小 | ~5-15MB (WebView 复用系统) | ~100-200MB (Chromium 捆绑) |
| 跨平台 | Windows/macOS/Linux 原生 | 同 |
| Python 集成 | 壳→子进程调 runtime (边界清晰) | 同模式, 但壳更大 |
| 自动更新 | tauri-updater 内置 (签名) | electron-updater |
| 商业化 | 原生性能 + 小包 + 签名分发友好 | 成熟但重 |
| 生态成熟度 | 较新 (2021+) 但 GitHub 主流采用 | 成熟 |

**推荐: Tauri 2.x**

理由：
1. 安全：Rust 壳 + 子进程边界 = 最小攻击面（契合"默认安全"）
2. 包小：下载安装体验好（v1.0 目标"下载即用"）
3. Python 集成模式清晰：Tauri Shell → factory-runtime (PyInstaller 捆绑二进制) → Core/Console 子进程
4. 自动更新内置（签名更新通道）
5. 未来商业化（21 Cloud/收费）原生支持

风险：Rust 构建链（cargo）——CI 打包标准化即可；WebView 版本差异（Edge/WebKitGTK）——目标平台验证。

## 3. Desktop 架构设计

```
┌─────────────────────────────────────────────┐
│ Tauri Desktop Shell (Rust)                  │
│  ├── WebView (React UI 复用 11B 前端)       │
│  └── commands (invoke → runtime bridge)     │
├─────────────────────────────────────────────┤
│ factory-runtime (PyInstaller 捆绑 Python)   │
│  └── RuntimeManager                         │
│       ├── Core CLI 子进程                   │
│       └── Console uvicorn 子进程            │
├─────────────────────────────────────────────┤
│ 数据目录 <data_root>/ (config/logs/data)    │
└─────────────────────────────────────────────┘
```

### 启动流程
```
用户双击 → Tauri 壳 → 启动 runtime (捆绑 Python) → RuntimeManager
  → 检查/初始化数据目录 (首次: 默认配置 + demo 数据)
  → 启动 Core (后台) → 启动 Console (uvicorn 127.0.0.1:<port>)
  → 健康检查 → WebView 加载 Console → UI READY
```

### 停止流程
```
窗口关闭 → Tauri 确认 → runtime 停止 (Console graceful → Core graceful)
→ 数据 flush → 退出
```

### 崩溃恢复
```
Core/Console 崩溃 → watchdog 重启 (≤3 次) → 事件记录
UI 崩溃 → WebView 重载
Runtime 崩溃 → 系统重启后数据完整 (原子写已保证 1-14 全部 store)
```

### 日志查看
```
Desktop 设置面板 → 读取 <data_root>/logs/*.log (tail)
统一: runtime.log + core.log + console.log
```

### 用户数据隔离
```
每用户独立 <data_root>; 项目数据在 <data_root>/data/.factory/
Console 只读 API (11A 铁律) → 用户只能经 UI 观察/审批, 不可越权
```

## 4. 配置系统设计（为 Phase 16 预留）

```
<data_root>/config/config.yaml     用户配置 (runtime/console/默认 provider)
<data_root>/providers/             Provider 配置 (Phase 16: 每家一个 yaml)
<data_root>/agents/                Agent 配置 (Phase 16)
<data_root>/skills/                Skill 配置 (Phase 16)
<data_root>/mcp/                   MCP 配置 (Phase 16)
<data_root>/logs/                  日志
<data_root>/data/.factory/         工厂数据 (已有结构)
```

三层合并：默认 (package) < 用户 (<data_root>/config) < 项目 (.factory/config, CLI 模式)。
Phase 16 Registry 只需向 providers/agents/skills/mcp 目录写声明式 yaml —— **Phase 15 目录结构先行，未来扩展零破坏**。

## 5. 安全边界设计（Phase 15 最小，默认安全）

```
- 用户数据: <data_root>/data (权限 700/750; Windows 用户 ACL)
- Console 绑定: 127.0.0.1 回环 + 随机 token 头 (防局域网访问)
- Secret (Phase 15 最小): 环境变量/Keychain, 禁明文入 yaml/日志/事件
  (Phase 18 完整 Secret Management)
- Runtime 权限: 最小 (只启动/停止/日志, 不触碰业务写路径)
- 默认拒绝: 无配置 provider = 不连接外部 (禁意外外呼)
- 更新: 手动确认 + 签名验证 (不执行未知代码)
```

## 6. Release 1.0.0 目标定义

```
Phase 15 完成后用户应能:

Windows: 下载 msi → 安装 → 启动 → 打开 Console → 运行 Demo (无需 git/python/node/npm)
macOS:   下载 dmg → 拖入 Applications → 启动 → Console → Demo
Linux:   deb/AppImage → 安装 → 启动

不需要: git / python / node / npm / 任何源码操作
```

## 7. 版本规划

**Phase 15 完成后 = v1.0.0 正式版（建议）**

```
v1.0.0 必须包含:
  ✅ Desktop App (Tauri, 3 平台)
  ✅ factory-runtime (进程管理/配置/数据目录/日志)
  ✅ Provider 基础配置 (hermes + 通用模板)
  ✅ Demo (factory demo markpad 内置)
  ✅ 文档 (安装/使用/演示/FAQ)
  ✅ 更新通道 (签名)
```

理由：RC (14B) 已收集反馈 → 15 提供安装体验 → 正式版发布条件齐备。

## 8. 风险分析

| 风险 | 缓解 |
|:-----|:-----|
| Rust 构建链复杂 | CI 标准打包 (tauri-action); 本地 macOS 先验证 |
| WebView 版本差异 | 目标平台兼容测试 (Win10+/macOS 12+/Ubuntu 22.04+) |
| PyInstaller 兼容性 | 提前 smoke (捆绑后跑 demo); 降级方案: 内置 python 解释器 (app-bundled) |
| Console 端口冲突 | 动态端口 + 重试; 健康检查 |
| 数据目录迁移 (旧 .factory) | datadir.migrate (复制+校验, 不破坏原数据) |
| 自动更新失败 | 手动下载回退 (release 页) |

## 9. 验收标准

```
1. 新用户流程: 安装包 → 启动 → Console 打开 → demo markpad 跑通 (无源码/无 CLI 操作)
2. runtime: start/stop/status/restart/logs CLI + 崩溃重启 (watchdog) 测试
3. 配置: 三层合并 + Phase 16 目录结构就位 (providers/agents/skills/mcp 空目录可写)
4. 安全: 127.0.0.1 + token; Secret 无明文扫描测试; 数据目录权限测试
5. 打包: macOS dmg 实机验证; Windows msi/Linux deb CI 或交叉验证 (至少 1 平台完整)
6. 测试: 新增 ≥80, pytest 4111+ 不回归; 前端 92+ 不回归
7. Core 零修改 (git diff 验证); Extension 独立 (Removal Isolation)
```

## 10. 开发顺序 (确认后 15A 实现)

```
15A-1 runtime 核心 (manager/launcher/config/datadir/logging/health)  [+60 tests]
15A-2 runtime CLI (start/stop/status/logs/demo) + watchdog            [+40 tests]
15A-3 Tauri Shell (壳 + 内嵌 Console + 打包 macOS dmg)               [+前端复用]
15A-4 Installer/更新 + 3 平台打包                                      [CI]
```
