# S10-026 Design Review — Product Bootstrap Foundation (v1.1)

> 日期:2026-08-14 | 状态:待确认 (v1.1 修订版) | 前置:S10-025 Product Entry Audit ✅ + v1.0 设计
> 目标:AI Factory 从"开发者工程项目"升级为"用户可运行产品"
> 约束:① 禁止新增 AI 能力 ② 不修改 Router/Agent/Runtime 核心 ③ 最大化复用已有资产 ④ 保持未来模块独立产品化能力
> v1.1 修订:按用户 5 条补充约束调整 —— ① config.json 禁存 LLM 偏好 ② doctor 可扩展框架 ③ Demo 隔离 workspace ④ CLI 唯一入口+命令组 ⑤ start 为 Runtime Manager

---

## 1. 当前 CLI 结构分析(取证,与 v1.0 一致)

### 1.1 三个 CLI 入口(现状)

```
入口 1: ./bin/factory (578 行, cli_factory.py)     ← 统一入口目标
  ✅ start / stop / status (真实可用)
  ❌ init / config / project / run (STUB_COMMANDS)

入口 2: .venv/bin/factory (org CLI, factory-org/org/cli.py)
  ✅ company / employee / authority / knowledge / artifact / workflow / approval / project

入口 3: exec CLI (factory-exec/exec/cli.py)
  ✅ run / status / providers / approval
```

### 1.2 复用资产(不变)

LLMControlPlane(S10-021)/ ModelCatalog(S10-022)/ LLMRouter+AgentPolicyStore(S10-024)/ create_app(static_dir)/ frontend dist / ConfigProvider 分层

## 2. 新命令架构(v1.1 修订)

### 2.0 CLI 定位:唯一用户入口 + 命令组命名空间(修订 ④)

```
./bin/factory                        # 唯一用户入口 (内部 org/exec 保留, 但用户只经此)
│
├── init           [P0] 首次运行初始化
├── doctor         [P1] 可扩展诊断框架 (修订 ②)
├── config         [P2] Factory Runtime Configuration (修订 ①: 只管理运行时配置)
├── start          [P3] Runtime Manager (修订 ⑤: 不绑定 backend/frontend)
├── stop / status  (现有)
│
└── 未来命令组 (预留, 本 Sprint 不实现):
    factory org      → 组织域 (现有 org CLI 代理)
    factory agent    → Agent 管理
    factory task     → 任务管理
    factory router   → LLM Router 管理
    factory rag      → RAG 管理
```

**命令组设计**:CLI 顶层子命令按产品域划分;当前已有功能先落在 `factory org` / `factory task` 等组下,内部代理现有 org/exec CLI 实现(薄代理,不重写)。本 Sprint 只建命名空间骨架 + P0~P3 核心命令。

### 2.1 P0:factory init(首次运行初始化)

```
factory init [--force] [--non-interactive] [--provider deepseek] [--model deepseek-chat]

流程 (不变, 但 LLM 配置写入目标按修订 ①):
1. 环境检测 (复用 _env_problems/_dep_problems)
2. workspace 初始化: ~/.factory/{agents,skills,projects,providers,workspace} 目录就位 (幂等)
3. LLM 配置引导:
   - providers.json (LLMControlPlane 管理) ← 交互创建 provider 条目
   - config.json 只写运行时: {data_dir, port, frontend_port} ← 不写任何 llm.* 偏好 (修订 ①)
4. 校验 (复用 ProviderConfigChecker)
5. 输出下一步: factory doctor / factory start
```

### 2.2 P1:factory doctor — 可扩展诊断框架(修订 ②)

```
factory doctor [<checker>...] [--verbose] [--json]

架构: 检查器注册表 (Checker Registry), 非硬编码五维
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class DoctorCheck(Protocol):
    id: str                    # "environment" / "provider" / "model" / "runtime" / "router"
    label: str                 # 人类可读名
    def run(self, ctx: DoctorContext) -> CheckResult
        # CheckResult: {id, status: OK|WARN|ERROR, message, detail?}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
内置检查器 (本 Sprint 实现):
  environment  → python/venv/node/npm (复用 _env_problems)
  provider     → providers.json 存在/enabled/key (复用 LLMControlPlane)
  model        → models.json 存在/种子/enabled (复用 ModelCatalog)
  runtime      → 8011/5180 端口/进程 (复用 _backend_running)
  router       → route() 无参数命中层 (复用 LLMRouter)

预留检查器 (注册表空位, 本 Sprint 不实现, 未来模块注册):
  ai-provider  → AI Provider 专项诊断 (未来)
  rag          → RAG 索引/检索诊断 (未来)
  governance   → 治理/审批链诊断 (未来)
  agent-policy → agent.yaml/skill.yaml 诊断 (未来)

退出码: 全 OK → 0; 有 WARN → 0 (带 ⚠); 有 ERROR → 1; 检查器不存在 → 2
扩展方式: 新模块实现 DoctorCheck 协议 → 注册到 registry → factory doctor 自动发现
```

### 2.3 P2:factory config — Factory Runtime Configuration(修订 ①)

```
factory config show              # 显示运行时配置 (data_dir/port/frontend_port) + 只读展示 LLM 状态
factory config set <key> <val>   # 写运行时配置 (仅允许 data_dir/port/frontend_port 白名单)
factory config path              # 显示配置文件路径

⚠️ 禁止写: llm.provider / llm.model / llm.base_url / llm.api_key_ref (修订 ①)
   LLM 偏好唯一来源:
   - Provider 生命周期 → providers.json (LLMControlPlane)
   - 项目规则 → project.yaml (LLMRouter L3)
   - Agent/Skill 策略 → agent.yaml/skill.yaml (LLMRouter L2)
   - config.json 定位 = Factory Runtime Configuration (端口/目录/环境)

扩展位 (仅预留注释, 不实现):
  config.json 未来可含: {runtime, services, demo} 等运行时段 — 无 llm.* 偏好段
```

### 2.4 P3:factory start — Runtime Manager(修订 ⑤)

```
factory start [service...]       # 启动指定服务 (缺省 = 全部已注册服务)
factory start --list             # 列出 services registry
factory stop [service...]
factory status

架构: Services Registry (服务注册表), 不硬编码 backend/frontend
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ServiceDef:                # 服务定义
    id: str                      # "backend" / "frontend" / "runtime" (未来更多)
    label: str
    required: list[str]          # 依赖服务
    start(ctx) -> ServiceHandle  # 启动
    stop(handle) -> None         # 停止
    health(ctx) -> bool          # 健康检查

内置服务 (本 Sprint 实现):
  backend  → uvicorn + create_app(factory_root)  [现有 _start_backend 迁入]
  frontend → 优先托管 dist (SPA), --dev 走 vite  [现有 _start_frontend 改造]
  runtime  → 沙箱 runtime 实例 (S10-023 已有能力, 可选)

未来服务 (注册表扩展位):
  vector-db → RAG 向量库 (未来)
  gateway   → 外部网关 (未来)

不绑定: start 是"启动服务注册表中的服务", backend/frontend 只是首批内置服务
```

### 2.5 P4:Demo — 隔离 Demo Workspace(修订 ③)

```
factory demo init                # 创建隔离 Demo Workspace
factory demo reset               # 重置 Demo (清空 → 重新 seed)
factory demo status              # Demo 状态

架构: Demo Workspace 隔离
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 数据根: ~/.factory-demo/ (独立于 ~/.factory/, 零污染用户数据) (修订 ③)
- seed: providers.json + models.json + 1 个示例项目 (复用 org project register)
- reset: 删除 ~/.factory-demo/ 重建 (demo 专用, 不碰 ~/.factory)
- 展示: 完整 AI Factory 流程 — Idea → Project → Workflow → Agent 执行 → Artifact (真实链路, S10-023 已通)
- 启动: factory demo start → 用 ~/.factory-demo 作 factory_root 起 backend+frontend
- 隔离保证: 用户 ~/.factory/ 数据零触碰; 可随时 reset
```

## 3. 配置模型设计(v1.1 修订)

### 3.1 分层不变

```
进程 env > 项目 .env > ~/.factory/config.json > 默认值 (ConfigProvider)
```

### 3.2 配置文件职责矩阵(修订 ① 核心)

| 文件 | 职责 | 管理者 | 可否被 config 命令写 |
|---|---|---|---|
| ~/.factory/config.json | **Factory Runtime Configuration** (data_dir/port/frontend_port/未来 services/demo) | factory config | ✅ 仅运行时白名单 |
| ~/.factory/providers.json | Provider 生命周期 (enabled/models/api_key_ref/metadata) | LLMControlPlane | ❌ 经 ControlPlane 专用命令 |
| ~/.factory/models.json | Model 元数据 (capabilities/context/cost/enabled) | ModelCatalog | ❌ 经 ModelCatalog |
| project.yaml | 项目级路由规则 (L3) | LLMRouter | ❌ 项目文件 |
| agent.yaml / skill.yaml | Agent/Skill 策略 (L2) | AgentPolicyStore | ❌ 角色文件 |

**单一来源原则**:LLM 决策链的每个输入只有一个权威来源,config.json 不参与 LLM 偏好
(Router 的 L1 用户指定来自调用参数,L2~L5 各有其文件——config.json 若存 LLM 偏好会成第 6 个来源,多源冲突)。

### 3.3 config.json 结构(v1.1)

```json
{
  "core": {
    "data_dir": "~/.factory",
    "port": 8011,
    "frontend_port": 5180
  },
  "runtime": { },        // 未来: 运行时配置 (服务注册表偏好)
  "demo": { }            // 未来: Demo workspace 配置
  // ⚠️ 无 llm.* 偏好段 — LLM 配置归 providers.json + policy 文件
}
```

## 4. 文件修改范围(v1.1)

### 新增文件
1. `factory-console/cli_doctor.py`(~250 行)— DoctorCheck 协议 + 注册表 + 5 内置检查器 + 预留空位
2. `factory-console/cli_services.py`(~200 行)— ServiceDef 协议 + services registry + backend/frontend/runtime 服务
3. `factory-console/cli_demo.py`(~180 行)— Demo Workspace 管理 (隔离根/seed/reset/start)
4. `tests/console/test_cli_init.py`(~15 cases)
5. `tests/console/test_cli_doctor.py`(~15 cases)
6. `tests/console/test_cli_config.py`(~10 cases)
7. `tests/console/test_cli_services.py`(~10 cases)
8. `tests/console/test_cli_demo.py`(~12 cases)

### 修改文件
9. `factory-console/cli_factory.py`(+250 行)— init/config 转正 + doctor/services/demo 注册 + 命令组骨架 + start 改造为 Runtime Manager(现有 start/stop/status 逻辑迁入 services registry,行为兼容)
10. `docs/README.md` 首次运行指引更新

### 不动(约束 2/3)
- llm_control.py / model_catalog.py / llm_router.py / agent_policy.py
- factory-exec/exec/ 全部;factory-core/ 全部
- org CLI / exec CLI(未来经 factory org/factory task 薄代理,本 Sprint 只建骨架)

## 5. 测试方案(v1.1)

| 文件 | 覆盖 |
|---|---|
| test_cli_init.py | 引导生成 providers.json;config.json 只写运行时白名单(**断言不写 llm.***);幂等;--non-interactive |
| test_cli_doctor.py | 5 内置检查器;注册表可扩展(注入假检查器自动被发现);exit code 0/1/2;--json 输出 |
| test_cli_config.py | show 脱敏;set 白名单(port 可写, llm.provider **拒绝**);path |
| test_cli_services.py | services registry;start backend 健康;start --list;stop;不存在的服务 → 明确错误 |
| test_cli_demo.py | 隔离根 (~/.factory-demo 不碰 ~/.factory);seed 后 providers/models 就位;reset 清空重建;status |

## 6. 迁移风险(v1.1 新增修订风险)

| 风险 | 等级 | 对策 |
|---|---|---|
| start 改造为 Runtime Manager 破坏现有 start 体验 | 中 | 行为兼容:start 无参数 = 启动全部内置服务 (backend+frontend), 与现有一致;服务化是内部重构, CLI 契约不变 |
| config 白名单过严用户困惑 | 低 | 清晰错误消息 + config set 帮助;LLM 配置引导在 init 完成 |
| demo workspace 隔离不完全 | 高 | 测试断言 demo 操作不触碰 ~/.factory;demo root 注入所有调用 (factory_root 参数) |
| doctor 框架过度设计 | 低 | 协议最小 (id/label/run/CheckResult);预留空位只是注册表注释,不建抽象层 |
| 命令组命名空间破坏现有脚本 | 中 | 现有 start/stop/status/init/config 保持顶层 (不移动);org/agent/task 等新组是**新增**,不破坏旧命令 |

## 7. 不做事项(v1.1 更新)

| # | 不做 | 理由 |
|---|---|---|
| 1 | 不新增 AI 能力 | 约束 1 |
| 2 | 不改 Router/Agent/Runtime/ModelCatalog/ControlPlane 核心 | 约束 2 |
| 3 | 不实现 project/run 完整功能 | 本 Sprint 聚焦 bootstrap;命令组骨架先建 |
| 4 | 不做 API 认证 | Sprint P2-01 |
| 5 | 不改前端 UI | 17 页面已可用 |
| 6 | 不打包/DMG/pipx | Sprint P3 |
| 7 | 不写 RAG/Governance/Agent Policy 诊断逻辑 | doctor 只留注册表空位 |
| 8 | 不建账号/权限 | 单机定位 |
| 9 | 不把 LLM 偏好写进 config.json | 修订 ① 红线 |
| 10 | 不迁移现有 org/exec CLI 代码 | 只建 factory org/task 薄代理骨架 |

## 8. 实施顺序(v1.1)

```
1. cli_doctor.py (可扩展框架 + 5 内置检查器) + 测试        [P1, 零风险纯新增]
2. cli_services.py (services registry) + 测试             [P3 基础]
3. cli_factory.py: doctor/services 注册 + start 改造 (行为兼容) [~1.5 天]
4. cli_factory.py: init 转正 + 测试                       [P0, ~1.5 天]
5. cli_factory.py: config 转正 (白名单) + 测试             [P2, ~1 天]
6. cli_demo.py (隔离 workspace) + 测试                    [P4, ~1 天]
7. README 更新 + 全量回归 + commit + push + report
```

> 总估: 单人 ~5-6 工作日; 每 Task 独立 commit (Sprint 纪律)
> v1.1 修订已按 5 条用户约束落实: config 禁 LLM 偏好 / doctor 可扩展 / demo 隔离 / CLI 唯一入口+命令组 / start Runtime Manager

---

> Design Review v1.1 完毕 | 待确认后开始实现
