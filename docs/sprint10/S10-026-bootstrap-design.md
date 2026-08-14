# S10-026 Design Review — Product Bootstrap Foundation

> 日期:2026-08-14 | 状态:待确认 | 前置:S10-025 Product Entry Audit ✅
> 目标:AI Factory 从"开发者工程项目"升级为"用户可运行产品"
> 约束:① 禁止新增 AI 能力 ② 不修改 Router/Agent/Runtime 核心 ③ 最大化复用 ControlPlane/ModelCatalog/Runtime ④ 保持未来模块独立产品化能力

---

## 1. 当前 CLI 结构分析(取证)

### 1.1 三个 CLI 入口(现状)

```
入口 1: ./bin/factory (578 行, cli_factory.py)     ← 统一入口目标
  ✅ start / stop / status (真实可用)
  ❌ init / config / project / run (STUB_COMMANDS)
  已有: 环境检测 _env_problems / 依赖检测 _dep_problems / 配置提示 _config_hints
        / 端口管理 / pid 文件 / 后端 uvicorn 启动 (base64 bootstrap) / 前端 vite dev

入口 2: .venv/bin/factory (org CLI, factory-org/org/cli.py)
  ✅ company / employee / authority / knowledge / artifact / workflow / approval / project
  定位: 组织域管理 (公司/员工/审批/产物) — 经 editable install 安装

入口 3: exec CLI (factory-exec/exec/cli.py)
  ✅ run / status / providers / approval
  定位: 执行域 (任务执行/Provider 预检/审批门)
```

### 1.2 关键复用资产(已建,直接可用)

| 资产 | 位置 | S10 | 复用点 |
|---|---|---|---|
| LLMControlPlane | factory-console/llm_control.py | 021 | config 读取/校验/持久化 (providers.json) |
| ModelCatalog | factory-console/model_catalog.py | 022 | model 查询/能力过滤 (models.json) |
| LLMRouter | factory-console/llm_router.py | 024 | 五层决策链 (route) |
| AgentPolicyStore | factory-console/agent_policy.py | 024 | agent.yaml/skill.yaml 读取 |
| 后端 FastAPI | fastapi_adapter.create_app(factory_root) | — | start 已用;静态托管已支持 (dist → SPA) |
| 前端 dist | frontend/dist (已构建 8-13 05:13) | — | start 产品化: 优先托管 dist |
| 配置分层 | config.py ConfigProvider | — | env > .env > config.json > 默认 |

### 1.3 核心问题(承接 S10-025)

1. **4 个 stub 命令**(init/config/project/run)— 首次运行无引导
2. **LLM 配置无向导** — 新用户 start 后执行必诚实 FAILED
3. **前端依赖 npm/vite dev** — dist 已构建但 start 不用它
4. **3 CLI 入口分裂** — 用户困惑
5. **无健康诊断** — 出问题只能看日志

## 2. 新命令架构

### 2.1 目标命令树(./bin/factory 统一)

```
./bin/factory
├── init         [P0] 首次运行初始化 (环境检测 + workspace + LLM 引导) ★ 本 Sprint
├── doctor       [P1] 环境/Provider/Model/Runtime 健康诊断          ★ 本 Sprint
├── config       [P2] 统一配置入口 (show/set-provider/check)        ★ 本 Sprint
├── start        [P3] 产品化启动 (backend + frontend + runtime)
├── stop         (现有)
├── status       (现有)
├── project      (stub → 代理 org/exec CLI)
└── run          (stub → 代理 exec CLI run)
```

### 2.2 P0:factory init(本 Sprint 最高优先)

```
factory init [--force] [--non-interactive] [--provider deepseek] [--model deepseek-chat]

流程:
1. 环境检测 (复用 _env_problems/_dep_problems): python/node/venv/node_modules
   → 缺失 → 明确指引 (先跑 setup.sh)
2. workspace 初始化: 确保 ~/.factory/{agents,skills,projects,providers,workspace} 目录
   → 首次创建 + 记录 (幂等, 重复执行安全)
3. LLM 配置引导 (复用 LLMControlPlane):
   a. 已存在 providers.json → 显示当前配置 + 询问是否修改
   b. 不存在 → 交互式创建 (provider 选择 → base_url 默认 → api_key_ref 引导)
   c. --non-interactive → 用参数生成
4. 配置校验 (复用 ProviderConfigChecker): key 可解析? model 存在?
5. 输出: 下一步提示 (factory start / factory doctor)
```

### 2.3 P1:factory doctor(诊断)

```
factory doctor [--verbose]

输出 (复用已有资产, 零新逻辑):
┌─ 环境 ──────────────────────────────────────
│ Python 版本 / venv / node / npm (复用 _env_problems)
├─ Provider ──────────────────────────────────
│ providers.json 存在? 每个 provider enabled? key 可解析?
│ (复用 LLMControlPlane.list_providers/resolve_api_key)
├─ Model ─────────────────────────────────────
│ models.json 存在? 种子已写入? enabled 模型数?
│ (复用 ModelCatalog.list_models)
├─ Runtime ───────────────────────────────────
│ 8011/5180 端口状态? 后端进程? 前端进程?
│ (复用 _backend_running/_frontend_running)
├─ Router ────────────────────────────────────
│ route() 无参数 → 命中哪层? (L5 fallback?)
│ (复用 LLMRouter.route)
└─ 结论: ✅ 就绪 / ⚠️ 有警告 / ❌ 有阻塞 (exit code 0/1/2)
```

### 2.4 P2:factory config(统一配置入口,为未来扩展)

```
factory config show                     # 显示当前配置 (脱敏: key 只显示 ref)
factory config set-provider <id>       # 设置默认 provider (复用 LLMControlPlane)
factory config set-model <model>       # 设置默认 model
factory config check                   # 校验配置 (复用 ProviderConfigChecker)
factory config path                    # 显示配置文件路径

设计: 配置写入 ~/.factory/config.json (ConfigProvider 已支持的分层)
      + providers.json (LLMControlPlane 已支持)
      → 零新配置体系, 扩展位: llm.router / llm.rag / llm.governance / llm.agent_policy
      (config.json 的 llm 段天然支持嵌套 — 未来模块直接加子段)
```

### 2.5 P3:factory start 产品化

```
变更:
1. 后端: 保持现有 (uvicorn + create_app(factory_root) — 已验证)
2. 前端: 优先托管 dist (create_app(static_dir=frontend/dist) → SPA)
         → npm 仅用于 build; 运行时零 node 依赖
3. 新增加载判断: dist 存在 → 生产形态; dist 缺失 → 提示 npm run build
4. runtime: 可选 --with-runtime 启动沙箱 runtime (S10-023 已有)

不改变: start 的幂等/端口预检/健康检查逻辑 (已验证可用)
```

### 2.6 P4:Demo Seed(首次运行体验)

```
factory init 完成后自动:
1. 写入 models.json 种子 (ModelCatalog 已有 — 首次 load 自动写入, 零代码)
2. 创建示例 agent.yaml? 不 — 保持最小: 只确保 providers.json + models.json 就位
3. 提示: factory doctor 验证 + factory start 打开 UI
4. 可选 --demo: 创建 1 个示例项目 (复用 org CLI project register)

判断: seed 最小化 — 不引入"假数据", 只做"配置就位"。demo 项目走真实 workflow。
```

## 3. 配置模型设计

### 3.1 分层不变(复用 ConfigProvider)

```
进程 env > 项目 .env > ~/.factory/config.json > 默认值
```

### 3.2 配置文件(两个,职责分离,均已存在机制)

| 文件 | 内容 | 管理者 |
|---|---|---|
| ~/.factory/config.json | 通用配置 (llm.provider/model/base_url/api_key_ref + 未来 router/rag/governance/agent_policy 子段) | factory config |
| ~/.factory/providers.json | Provider 生命周期 (enabled/models/api_key_ref/metadata) | LLMControlPlane (S10-021) |
| ~/.factory/models.json | Model 元数据 (capabilities/context/cost/enabled) | ModelCatalog (S10-022) |

### 3.3 config.json llm 段扩展位(为未来模块预留,不实现)

```json
{
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "router":    { },   // 未来: Router 配置
    "rag":       { },   // 未来: RAG 配置
    "governance": { },  // 未来: 治理配置
    "agent_policy": { } // 未来: Agent Policy 配置
  }
}
```

> 约束 ④"保持未来模块独立产品化能力": config 只做统一入口 + 分层合并,不绑定具体模块;
> 每模块继续用自己已有配置文件 (providers.json/models.json/agent.yaml),config 是"总览+引导"。

## 4. 文件修改范围

### 新增文件
1. `factory-console/cli_doctor.py`(~200 行)— factory doctor 实现 (纯复用现有资产)
2. `tests/console/test_cli_init.py`(~15 cases)— init 引导/幂等/非交互
3. `tests/console/test_cli_doctor.py`(~12 cases)— doctor 诊断各维度/exit code
4. `tests/console/test_cli_config.py`(~10 cases)— config show/set/check/脱敏

### 修改文件
5. `factory-console/cli_factory.py`(+150 行)— 4 个 stub 转正 (init/config/doctor) + parser 注册
   - 保持: start/stop/status 现有逻辑零改动
   - 复用: _env_problems/_dep_problems/_backend_running 等现有辅助
6. `factory-console/web/backend/fastapi_adapter.py`(+10 行)— 无改动? 不需要
   (create_app 已支持 static_dir; start 调用时传即可 — **确认零修改**)
7. `docs/README.md` 首次运行指引更新(4 步: setup → init → doctor → start)

### 不动(约束 2/3)
- factory-console/llm_control.py / model_catalog.py / llm_router.py / agent_policy.py
- factory-exec/exec/ 全部
- factory-core/ 全部
- org CLI / exec CLI(project/run 转正只做薄代理,不重写)

## 5. 测试方案

| 测试文件 | 覆盖 |
|---|---|
| test_cli_init.py | ① 无 providers.json → 交互引导生成 ② 已存在 → 幂等提示 ③ --non-interactive + 参数 → 直接生成 ④ workspace 目录创建 ⑤ 损坏 providers.json → 修复引导 |
| test_cli_doctor.py | ① 环境就绪 → exit 0 ② 缺 key → ⚠️ 非阻塞 ③ 无 providers.json → ❌ 阻塞 ④ 后端运行检测 ⑤ Router fallback 诊断 |
| test_cli_config.py | ① show 脱敏 (key 只显示 ref) ② set-provider 持久化 ③ check 返回状态 ④ path 显示 |

关键测试原则(沿用项目铁律):
- 全部 tmp_path 隔离 (HOME 重定向),不写真实 ~/.factory
- 复用 tests/console/ 既有装配模式 (importlib + sys.path)
- init/config 的 LLM 交互用注入 env/monkeypatch 模拟

## 6. 迁移风险

| 风险 | 等级 | 对策 |
|---|---|---|
| init 误写用户真实 ~/.factory | 高 | 测试全部 tmp 隔离;生产首次运行提示"将写入 ~/.factory,确认?" |
| config 与 providers.json 双配置源冲突 | 中 | 明确职责: config.json=通用入口, providers.json=Provider 生命周期;set-provider 只写 config.json,Provider 细节走 ControlPlane |
| start 切 dist 后开发热更新失效 | 中 | 保留 --dev 标志走 vite dev;默认生产形态用 dist |
| stub 转正破坏现有 start | 低 | start/stop/status 代码零改动,只加新子命令 |
| doctor 误报(端口被其他服务占用) | 低 | 只报状态不杀进程;提示检查 |
| 交互式引导在 CI/无 TTY 环境卡死 | 中 | --non-interactive 模式 + 环境无 TTY 时自动降级非交互 |

## 7. 不做事项(本 Sprint 明确不做)

| # | 不做 | 理由 |
|---|---|---|
| 1 | 不新增任何 AI 能力 | 约束 1 |
| 2 | 不改 Router/Agent/Runtime/ModelCatalog/ControlPlane 核心 | 约束 2 |
| 3 | 不实现 project/run 完整功能(只注册命令 + 薄代理) | 本 Sprint 聚焦 bootstrap;project/run 属 P1-04/05 单独 Sprint |
| 4 | 不做 API 认证 | 属 Sprint P2-01,另列 |
| 5 | 不做前端 UI 改动(除 start 托管方式) | 17 页面已可用 |
| 6 | 不做打包/DMG/pipx 安装器 | Sprint P3 |
| 7 | 不写 RAG/Governance/Agent Policy 配置逻辑 | 只预留 config.json 扩展位 |
| 8 | 不建账号/权限/多用户 | 单机产品定位 |

## 8. 实施顺序(本 Sprint)

```
1. cli_doctor.py + 测试 (纯新增, 零风险)          [P1 doctor 先行 — 无依赖]
2. cli_factory.py: doctor 注册 → 转正               [~1 天]
3. cli_factory.py: init 转正 + test_cli_init        [P0 核心, ~1.5 天]
4. cli_factory.py: config 转正 + test_cli_config    [P2, ~1 天]
5. start 产品化 (dist 托管 + --dev) + 验证          [P3, ~0.5 天]
6. README 更新 + 全量回归 + commit + push + report
```

> 总估: 单人 ~4-5 工作日; 每 Task 独立 commit (项目 Sprint 纪律)

---

> Design Review 完毕 | 待确认后开始实现 (Sprint 顺序: doctor → init → config → start 产品化)
