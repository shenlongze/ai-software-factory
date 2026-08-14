# S10-025 Reality Check — AI Factory Product Entry Audit

> 日期:2026-08-14 | 状态:只读取证,未修改代码 | 禁止:继续增加新 AI 能力
> 目标:分析 CLI/UI/install/start 状态,输出首次运行路径 / 缺失入口 / MVP 启动方案 / 产品化 Sprint 计划

---

## 1. 用户首次运行路径(现状实测)

### 现有入口盘点

| 入口 | 状态 | 实测证据 |
|---|---|---|
| `./bin/factory`(统一 CLI) | ✅ 可用 | `./bin/factory status` 实测退出 0,显示数据目录/LLM/端口状态 |
| `bash scripts/setup.sh`(安装) | ✅ 可用 | venv + editable install + 可选 frontend npm install + --check 就绪验证 |
| `bash scripts/demo.sh`(演示) | ✅ 可用 | 脚本化 MarkPad 生命周期演示(8 阶段) |
| `./bin/factory start`(启动) | ⚠️ 有实现 | 环境/依赖/端口预检 + 后端 uvicorn + 前端 vite dev + 浏览器 |
| `./bin/factory stop/status` | ✅ 可用 | pid 文件 + 端口探测 |
| `./bin/factory init/config/project/run` | ❌ **stub** | STUB_COMMANDS = ("init","config","project","run") — 打印预留提示 |
| 前端 UI | ⚠️ 部分 | 17 页面 + 21 Af 组件;dist 已构建(8-13 05:13);但 start 用 vite dev(需 npm) |
| 后端静态托管 | ✅ 可用 | build_app(static_dir) → SPA html=True;dist 存在时挂载 |

### 首次运行真实路径(用户会经历什么)

```
1. git clone ai-software-factory
2. bash scripts/setup.sh          → venv + pip install + npm install (幂等)
3. ./bin/factory start            → 后端 8011 + 前端 5180 + 打开浏览器
   └─ 但需要先配置 LLM: providers.json + api_key_ref (S10-021/023)
4. 浏览器打开 http://127.0.0.1:5180 → 17 页面 UI
```

**核心问题:步骤 3 依赖手工配置 LLM(providers.json),没有 `factory config` 引导;步骤 2 的 setup 不检查 LLM。**

## 2. 缺失入口(逐项)

| # | 缺失 | 影响 | 证据 |
|---|---|---|---|
| M1 | **`factory init` 是 stub** | 用户无首次初始化引导(数据目录/LLM 配置/示例项目) | cli_factory.py STUB_COMMANDS |
| M2 | **`factory config` 是 stub** | 无 LLM 配置向导;新用户不知道配 providers.json | 同上 |
| M3 | **`factory project` 是 stub** | 无法从 CLI 创建/管理项目 | 同上 |
| M4 | **`factory run` 是 stub** | 无法从 CLI 触发执行(真实执行只能走 API) | 同上 |
| M5 | **LLM 配置无引导** | 首次 start 后执行必然诚实 FAILED(除非手工写 providers.json + key 环境) | S10-023 实测:缺 key/project_dir 均 FAILED |
| M6 | **前端需 npm/vite dev**(生产形态未定) | start 依赖 node_modules;dist 已有但 start 不用它(用 vite dev) | cli_factory._start_frontend 用 npm run dev |
| M7 | **3 个 CLI 入口分裂** | ./bin/factory vs .venv/bin/factory(org CLI)vs exec CLI — 用户困惑 | 快照 §8 已记录 |
| M8 | **无一键安装产物**(DMG/pipx/brew) | 只能从源码跑;无 release 构建 | setup.sh 是源码安装 |
| M9 | **README 首次运行指引脱节** | README 说"7 页"但实际 17 页;demo 是终端脚本,UI 路径未文档化 | README.md:20 vs 实际 17 页面 |

## 3. MVP 启动方案(不做新 AI 能力)

### 原则
- 只补产品入口,不碰 AI 核心(S10-021~024 已冻结验收)
- 目标:新用户从 clone 到看到 UI + 真实执行,≤10 分钟,零手工配置

### 方案(按优先级)

```
MVP-A: factory init 转正 (最小初始化引导)
  - 首次运行检测:无 providers.json → 引导创建 (interactive: provider/model/base_url/api_key_ref)
  - 生成 ~/.factory/providers.json + 提示 key 注入方式 (env 引用, 不落明文)
  - 产出: init → config → start 三步走

MVP-B: factory config 转正 (LLM 配置管理)
  - config show / config set-provider / config check
  - 复用 LLMControlPlane (S10-021 已建, 零新逻辑)

MVP-C: start 前端用 dist 托管 (生产形态)
  - 后端 static_dir 已支持 (build_app 已验证) — start 改为优先托管 dist, vite dev 仅开发模式
  - 消除对 npm 的运行时依赖 (node 只用于 build)

MVP-D: 统一 CLI 入口
  - ./bin/factory 增加 project/run 子命令 (代理到 org/exec CLI 或 service API)
  - 消除 3 入口分裂
```

### 不做的(MVP 范围外)
- 不打包 DMG/安装器(后续)
- 不建账号/权限系统(API 认证是 P1,另列)
- 不重写前端 UI(17 页面已可用,只补入口引导)

## 4. 产品化 Sprint 计划

### Sprint P1 — 产品入口(预计 1-2 周,单人)

| Task | 内容 | 验收 |
|---|---|---|
| P1-01 | `factory init` 转正:首次初始化引导(数据目录 + providers.json 交互创建) | 新用户 clone → init → start → UI 可用 |
| P1-02 | `factory config` 转正:show/set-provider/check(复用 LLMControlPlane) | config show 显示 providers;set-provider 持久化 |
| P1-03 | start 前端切 dist 托管(vite dev 仅开发) | 无 npm 也能 start;浏览器打开 UI |
| P1-04 | `factory run` 转正:CLI 触发真实执行(代理 service API) | CLI 跑一次任务成功 |
| P1-05 | `factory project` 转正:CLI 项目 CRUD(代理 API) | project create/list/show |
| P1-06 | 3 CLI 统一:./bin/factory 代理 org/exec 子命令 | 一个入口覆盖全部 |
| P1-07 | README 首次运行指引更新(clone→init→config→start 四步) | 新用户按文档 10 分钟跑通 |

### Sprint P2 — 产品化加固(预计 1-2 周)

| Task | 内容 | 验收 |
|---|---|---|
| P2-01 | API 认证(至少 localhost token) | 非本机访问拒绝 |
| P2-02 | 前端执行触发(从 UI 下发任务,接线 S10-023 真实执行) | UI 点按钮 → 真实执行 → 审计可见 |
| P2-03 | LLM 配置 UI(前端配置页,替代手写 yaml/json) | UI 上配 provider/model/key_ref |
| P2-04 | 错误消息改进(execution_loop.py:796 project_dir vs provider key 区分) | S10-023 遗留 P2 项 |
| P2-05 | 示例项目 seed(init 时创建 1 个演示项目) | init 后 UI 有示例数据 |

### Sprint P3 — 发布准备(后续)

| Task | 内容 |
|---|---|
| P3-01 | release 构建(源码 tarball / pipx 安装) |
| P3-02 | 安装验证文档(干净环境从零安装) |
| P3-03 | 版本/更新机制 |

## 5. 结论

- **已有资产充足**:统一 CLI 骨架(bin/factory start/stop/status 真实可用)、安装脚本(setup.sh 幂等)、前端 17 页面 + dist 构建、后端静态托管能力——产品入口的基础设施都在
- **最大缺口**:4 个 stub 命令(init/config/project/run)+ LLM 配置无引导 + 前端运行时依赖 npm
- **MVP 关键判断**:S10-021 的 LLMControlPlane + S10-023 的真实执行链**已经存在**,MVP-A/B 只是把它们接到 CLI 引导,零新 AI 能力——完全符合"禁止新增 AI 能力"约束
- **建议**:直接开 Sprint P1(P1-01 init 转正 + P1-02 config 转正是最高优先,解锁"首次运行路径")

---

> Reality Check 完毕 | 未修改任何代码 | 待确认后 Design Review (Sprint P1 范围)
