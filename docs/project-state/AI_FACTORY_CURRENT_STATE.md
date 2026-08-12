# AI FACTORY CURRENT STATE — PROJECT STATE SNAPSHOT

> 快照日期: 2026-08-13 | Git HEAD: 7ea7bd4 (290 commits, main, origin push 同步)
> 目的: 电脑重启后, 新的 AI Agent (Hermes / Claude / Codex) 能快速理解整个项目
> 性质: 状态记录 (只整理/分析/记录, 不修改代码)
> 测试基线 (最新验证): pytest 7775 passed / vitest 669 passed (56 files) / tsc 0 error / build ✓

---

# 1. Project Identity

```
项目名称:  AI Software Factory
定位:      AI Software Company Operating System (AI 软件公司操作系统)
仓库:      https://github.com/shenlongze/ai-software-factory (私有)
本地:      /Users/Shared/work/ai-software-factory
核心目标:  让 AI Agent 像软件公司员工一样:
           理解需求 → 规划任务 → 执行开发 → 调用工具 → 产出软件 → 接受治理
关键区别:  不是 Agent Framework / Chatbot / Workflow Engine
           — 是"治理驱动的 AI 软件生产系统" (组织隐喻: 公司/部门/员工/项目)
```

# 2. Current Development Phase

```
Sprint: S10 (AI Employee Execution Layer)
完成:
  S10-014  Frontend Foundation (9/9 Task)     — 前端基础
  S10-015  Human Operating Interface (7/7)    — Dashboard/Project/Task/Workflow/Runtime/Quality Gate
  S10-016  AI Employee Runtime (2/2)          — Runtime Session + Agent Executor
  S10-017  Execution Loop (1/1)               — AgentExecutionLoop + Planner + AgentStep
  S10-018  Tool Runtime (1/1)                 — Tool Model/Registry/Executor + filesystem.read
  S10-019  Skill System (1/1)                 — Skill Model/Registry/权限链 + 3 内置 Skill
当前:
  S10-020  MCP Adapter (1/1) ✅ 已完成待审核    — MCPConnection/Adapter/Mock echo
未来 (未开始): Multi Agent / Memory / Learning Loop
```

# 3. Architecture Snapshot

```
┌────────────────────────────────────────────────────┐
│ Governance Layer (治理层)                            │
│  Permission Chain: Agent→Skill→Tool→MCP (Default Deny)│
│  Approval Gate / Human Decision / Review Feedback    │
├────────────────────────────────────────────────────┤
│ Audit Layer (审计层)                                 │
│  事件溯源 (SQLite ~/.factory/factory.db)            │
│  org.* / workflow.* / runtime_session.* / tool.* /   │
│  skill.* / mcp.* 事件 + console.viewed 审计          │
├────────────────────────────────────────────────────┤
│ Execution Layer (factory-exec)                      │
│  AgentExecutor → ExecutionLoop → Planner → Skill →   │
│  ToolExecutor → MCP Adapter → AgentRuntime → LLM     │
├────────────────────────────────────────────────────┤
│ Domain Layer (factory-core + factory-org)           │
│  Task/Project/Agent/Workflow/Artifact/Approval/      │
│  Capability/Experience                               │
├────────────────────────────────────────────────────┤
│ Console Layer (factory-console)                     │
│  FastAPI (75+ 端点) + service.py (4046 行)          │
│  CLI: bin/factory + org CLI + exec CLI              │
├────────────────────────────────────────────────────┤
│ Frontend Layer (React 18 + Vite)                    │
│  17 页面 + 21 Af 组件 + domain.ts (1391 行 Adapter)  │
├────────────────────────────────────────────────────┤
│ Data Layer (~/.factory/)                            │
│  SQLite (factory.db 事件) + JSON stores              │
│  agents/ org/ projects/ runtimes/ runtime-sessions/  │
└────────────────────────────────────────────────────┘
```

各层职责:
- **Governance**: 权限链 (Agent has Skill → Skill includes Tool → Tool Permission), 审批门, 最小权限表
- **Audit**: 全事件落库, Who/What/When/Model/Tool/Result
- **Execution**: 一次 AI 执行的生命周期编排 (Loop + Step + Event)
- **Domain**: 领域实体与业务规则
- **Console**: API + CLI 接口层
- **Frontend**: 人类控制面 (真实数据, 非 mock)
- **Data**: 持久化

# 4. Completed Features

```
Agent Runtime (S10-016):
  Status: ✅ 完成 | Location: factory-exec/exec/runtime_session.py (480 行)
  Verification: 51 pytest + curl 真实联调 (rs-3fb653f1)
  内容: RuntimeSession 5 态状态机 + RuntimeEvent 23 类型 + AgentStep + 原子写 Store

Agent Executor (S10-016):
  Status: ✅ 完成 | Location: factory-exec/exec/agent_executor.py (170 行)
  Verification: 12 pytest + curl POST /api/runtime/execute
  内容: Task→Session→LLM→Result 闭环; 无 LLM key → 诚实 FAILED

Execution Loop (S10-017):
  Status: ✅ 完成 | Location: factory-exec/exec/execution_loop.py (878 行)
  Verification: 39 pytest (含完整事件链保序)
  内容: CREATED→RUNNING→WAITING_DECISION|WAITING_ACTION→COMPLETED|FAILED;
        AgentStep 6 类型; MAX_ROUNDS=4 防循环; skill/mcp 事件条件触发

Tool Runtime (S10-018):
  Status: ✅ 完成 | Location: factory-exec/exec/tool.py (397) + tools/filesystem.py
  Verification: 35 pytest + curl (filesystem.read 成功/403/沙箱拦截)
  内容: Tool/ToolResult/ToolRegistry/ToolExecutor; filesystem.read 沙箱
        (相对路径强制/穿越拒绝/symlink 逃逸拒绝)

Skill System (S10-019):
  Status: ✅ 完成 | Location: factory-exec/exec/skill.py (420 行)
  Verification: 28 pytest + curl (GET /api/skills 3 个; backend-1→backend.development)
  内容: Skill/SkillRegistry/SkillContext; 权限链 3 环;
        3 内置 Skill (backend.development/testing/flutter.development)

MCP Adapter (S10-020):
  Status: ✅ 完成 (待审核) | Location: factory-exec/exec/mcp.py (442 行)
  Verification: 30 pytest + curl (POST connection → GET tools echo → Agent 调 echo)
  内容: MCPConnection/MCPClient Protocol/MockMCP echo/MCPToolAdapter/MCPRegistry
        注册即连接 (mcp_connected→discovered→registered); 禁连公网

CLI:
  Status: ⚠️ 部分 | Location: bin/factory + org/cli.py + exec/cli.py
  Verification: 无专项测试
  内容: start/stop/status 可用; project/run 是 stub

Frontend Console (S10-014/015):
  Status: ✅ 完成 | Location: frontend/src/ (17 页面 + 21 Af 组件)
  Verification: 669 vitest + tsc 0 + 浏览器实测
  内容: Workspace/Project Shell/Todo Tree/Workflow/Runtime/Dashboard/Quality Gate
        真实数据 (vite proxy → 8011), 四态组件, 诚实 Unavailable

API (全部):
  Status: ✅ 75+ 端点 | Location: factory-console/web/backend/fastapi_adapter.py
  Verification: 42 console pytest (导出) + 29 权限边界 + 18 mcp API
  内容: 见 §7 API Inventory
```

# 5. Current Execution Flow

```
User Task
  ↓ Task (backlog task 或 exec Task T-001)
  ↓ Agent (手工指定 agent_id — 无自动分配)
  ↓ Skill Loading (skill_loaded 事件, 条件触发)
  ↓ Planner (LLMPlanner — 无 LLM key → 诚实 FINAL 单轮)
  ↓ LLM Provider (❌ 当前无 key — 项目无 .env)
  ↓ Decision (decision_created 事件)
  ↓ Tool/MCP (tool_requested→started→completed; MCP echo 可执行; filesystem.read 沙箱)
  ↓ Observation (observation_received)
  ↓ Result (execution_completed|failed + output/summary/raw_response)
  ↓ Audit (全事件入 SQLite)

真实实现到哪里:
  ✅ 到 Tool/MCP 层可真实执行 (filesystem.read / MCP echo 实测成功)
  ⚠️ LLM Provider 层断裂: 无 key → LLMPlanner 诚实 FINAL → 单轮空转
  ❌ Memory / Learning / Feedback 未实现
```

# 6. Code Structure Map

```
/Users/Shared/work/ai-software-factory/
├── factory-core/          # 核心域 (~30K 行)
│   ├── agents/            #   Agent 模型/Registry/Skills/Store
│   ├── tasks/             #   Task 模型/Store (exec 域 T-001)
│   ├── projects/          #   项目模型
│   └── events/            #   事件模型/logger
├── factory-org/           # 组织域 (org 事件溯源)
│   └── org/               #   company/employee/authority/artifact/workflow/
│                          #   approval/management/projects/registry/cli
├── factory-exec/          # 执行域 (S10-016~020 核心)
│   └── exec/
│       ├── runtime_session.py   # Session 5 态 + Event 23 类型 + AgentStep
│       ├── agent_executor.py    # Task→Session→LLM→Result 编排
│       ├── execution_loop.py    # Loop 状态机 + Planner + SkillContext
│       ├── tool.py              # Tool Model/Registry/Executor
│       ├── tools/filesystem.py  # filesystem.read 沙箱
│       ├── skill.py             # Skill Model/Registry/权限链
│       ├── mcp.py               # MCPConnection/Adapter/Registry
│       ├── provider.py          # ProviderInterface/Registry/ConfigChecker
│       └── agent_runtime.py     # LLM 执行引擎 (DeveloperAgent + patch 验证)
├── factory-runtime/       # 沙箱执行环境
├── factory-console/       # Console 层
│   ├── service.py         #   4046 行 (所有 API 方法的失败安全装配)
│   ├── cli_factory.py     #   bin/factory CLI (start/stop/status + stubs)
│   ├── runtime_store.py   #   S10-004 RuntimeInstanceStore (browser|terminal)
│   ├── workflow_runner.py #   workflow 执行 (LLM key 装配)
│   ├── api/               #   路由函数模块 (projects/tools/skills/mcp/runtime_session/...)
│   └── web/backend/fastapi_adapter.py  # FastAPI 75+ 端点
│       └── frontend/src/  #   React 18 + Vite (25K 行)
│           ├── api/domain.ts     # 1391 行 Adapter (真实转换)
│           ├── api/client.ts     # API 封装
│           ├── components/af/    # 21 Af 组件 (Shell/Dashboard/TodoTree/QualityGate...)
│           ├── pages/            # 17 页面
│           ├── models/           # 类型
│           └── test/             # 56 vitest 文件
├── tests/                 # 332 pytest 文件 (7775 测试)
│   ├── exec/              #   执行域测试 (含 exec_helpers.py)
│   ├── console/           #   console 测试 (importlib 模式)
│   ├── runtime/           #   runtime 测试
│   └── org/ / core/       #   域测试
├── docs/
│   ├── sprint10/          #   S10-014~020 每 Task completion 报告
│   ├── design/            #   架构设计 (AF-UI-Architecture / S10-014-plan)
│   └── audit/             #   全量技术审查 (AI-FACTORY-CURRENT-STATE-REVIEW.md)
└── bin/factory            # CLI 薄包装
```

# 7. API Inventory

```
Method  Path                                        Purpose               Status
GET     /api/dashboard                              Control Center 数据   ✅
GET     /api/projects                              项目清单              ✅
POST    /api/projects                              创建项目              ✅
POST    /api/projects/suggest                      想法理解 (AI 建议)    ✅
POST    /api/projects/{id}/discovery/answer|complete 需求澄清            ✅
POST    /api/projects/{id}/confirm                 项目确认              ✅
PATCH   /api/projects/{id}                         更新项目              ✅
DELETE  /api/projects/{id}                         删除项目              ✅
POST    /api/projects/{id}/backlog/{epic|feature|story|task} 创建 backlog ✅
GET     /api/projects/{id}/backlog                  backlog 树           ✅
PATCH/DELETE /api/projects/{id}/backlog/task/{task_id} 任务更新/删除      ✅
POST    /api/projects/{id}/sprints|milestones|roadmap  规划 CRUD         ✅
GET     /api/projects/{id}/lifecycle               项目生命周期          ✅
GET     /api/projects/{id}/workflow                项目 workflow         ✅
GET     /api/projects/{id}/timeline                事件时间线            ✅
POST    /api/projects/{id}/start                   启动 workflow        ✅
GET     /api/projects/{id}/run-status              运行状态轮询          ✅
GET     /api/projects/{id}/runtimes                沙箱实例              ✅
POST    /api/projects/{id}/runtimes                创建沙箱              ✅
POST    /api/runtimes/{id}/start|stop|screenshot   沙箱控制              ✅
GET     /api/approvals /api/approval-gates         审批门清单            ✅
POST    /api/approvals/{id}/approve|reject         审批决定              ✅
GET     /api/artifacts[/{id}][/content]            产物                  ✅
GET     /api/decisions/{id}                        决策详情              ✅
GET     /api/providers                             Provider 配置预检     ✅
GET     /api/events/stream                         SSE 事件流            ✅
POST    /api/agents/{agent_id}/sessions           创建 Runtime Session  ✅
POST    /api/runtime-sessions/{id}/start|events|complete|cancel  生命周期 ✅
GET     /api/runtime-sessions[/{id}]               Session 查询          ✅
GET     /api/tasks/{task_id}/runtime               按 Task 查 Runtime    ✅
POST    /api/runtime/execute                       Agent 执行入口        ✅
GET     /api/tools                                 工具清单              ✅
POST    /api/tools/{tool_id}/execute               执行工具 (权限检查)   ✅
GET     /api/skills                                技能清单              ✅
GET     /api/agents/{agent_id}/skills              Agent 技能            ✅
GET     /api/mcp/connections                       MCP 连接清单          ✅
POST    /api/mcp/connections                       创建 MCP 连接         ✅
GET     /api/mcp/tools                             MCP 导入工具          ✅
```

# 8. CLI Status

```
入口: ./bin/factory (薄包装 → factory-console.cli_factory)

command        implemented?  working?  backend dependency  notes
start          ✅ 实现        ✅ 已验证 起 8011 + 前端      --no-browser/--port/--frontend-port
stop           ✅ 实现        ✅        杀进程 (pid 优先)    -
status         ✅ 实现        ✅        8011 探测          端口/进程/数据目录/LLM 状态
init           ❌ stub        未实现    -                   STUB_COMMANDS
config         ❌ stub        未实现    -                   预留
project        ❌ stub        未实现    -                   预留
run            ❌ stub        未实现    -                   预留

入口: factory-org/org/cli.py (.venv/bin/factory)
command        implemented?  working?  backend dependency  notes
company create/show        ✅    ✅  org 事件 API          公司模板实例化/详情
employee hire/list         ✅    ✅  org 事件 API          员工管理
authority check            ✅    ✅  org 事件 API          Default Deny 权限校验
knowledge add/list         ✅    ✅  org 事件 API          知识管理
artifact create/get/list/query/update/archive/validate  ✅  ✅  org 事件 API  阶段产物管理
workflow create/list/show/run/status  ✅  ✅  org 事件 API  工作流编排
approval list/show/approve/reject  ✅  ✅  org 事件 API     审批门
project register/show/list  ✅    ✅  org 事件 API         已有项目接入

入口: factory-exec/exec/cli.py
command        implemented?  working?  backend dependency  notes
run            ✅            ✅  exec API                执行请求→Runtime
status         ✅            ✅  exec API                执行结果查询
providers      ✅            ✅  exec API                Provider key 预检
approval approve/deny/apply/list  ✅  ✅  exec API       执行审批门禁

结论: 3 个 CLI 入口分裂; bin/factory 的 project/run 是 stub;
      org/exec CLI 完整可用但无自动化测试。
```

# 9. Provider & Model Status

```
Provider (已实现):
  ProviderInterface (generate request→response)          ✅ factory-exec/exec/provider.py
  ProviderRegistry (register/get 内存)                    ✅
  ProviderConfigChecker (key 预检 configured=True)         ✅
  ProviderConfigStatus (provider_id/display/key_var/configured) ✅

Provider (未实现):
  ❌ Provider 持久化 (配置存 ~/.factory/providers.json — 目录存在但空)
  ❌ 多 Provider 连接 (execute 用单一 self._provider())
  ❌ Provider 路由 (能力/成本/延迟/故障切换/负载均衡)

Model:
  ❌ 无 Model Registry (只有 provider_id, 无 model 名称/能力/context/cost)
  ❌ 无模型切换 (硬编码单一 provider)
  ❌ 无 Model Catalog

LLM 是否真实调用: ❌ 否
原因: 项目无 .env (后端 8011 无 ANTHROPIC/OPENAI/DEEPSEEK key);
      AgentRuntime.execute() 无 Provider → LLMPlanner 诚实 FINAL 单轮空转;
      唯一已配置 key: Hermes ~/.hermes/.env 有 DEEPSEEK_API_KEY (未接入项目)
影响: "AI 公司"当前是空转工厂 — 这是当前最大短板 (P0)
```

# 10. Governance Status

```
已落地:
  ✅ Identity: User (ALLOWED_USERS) / Project / Agent (registry) / Role (role_ids)
  ✅ Permission: Agent→Skill→Tool 3 环链 (check_tool_access)
     - backend-1→filesystem.read ✅ / flutter-dev→403 / ghost→403 (实测)
     - Skill 环: Skill 不含 tool → 拒绝; MCP 工具同链 (不绕过)
  ✅ Skill Permission: 3 内置 Skill + SYSTEM_AGENT_SKILLS 分配表
  ✅ Tool Permission: ToolPermissionPolicy (allow_all / 收窄白名单)
  ✅ Sandbox: filesystem.read workspace 沙箱 (穿越/编码/symlink 防护, 实测)
  ✅ Audit: 事件溯源 SQLite + AuditStore.append capability 字段
     {agent/skill/mcp/llm: {id, version}} + console.viewed 审计

缺失:
  ❌ 策略引擎 (权限硬编码 SYSTEM_AGENT_SKILLS, 无可配置策略)
  ❌ RBAC 声明文件 (角色→权限独立管理)
  ❌ 代码变更审批门 (execution approval 存在但未连 Quality Gate)
  ❌ 统一审计浏览器 (有记录无查询 API/前端)
  ❌ API 认证 (FastAPI 裸奔, 仅本机)
```

# 11. Testing Status (最新, 非历史)

```
pytest:  7775 passed (332 文件, 0 failed)   [最近全量确认]
         关键组快照: exec 6 文件 201 passed (Session 51/Loop 39/Tool 35/Skill 28/MCP 30/console 18)
vitest:  669 passed (56 文件, 0 failed)     [最新全量复跑]
tsc:     0 error                            [最新确认]
build:   ✓ (319KB, gzip 94KB)               [最新确认]
CI/CD:   ❌ 无 (全本地, 无 GitHub Actions)
```

# 12. Known Issues

```
P0:
  1. 无 LLM key 接入 — 项目无 .env; 执行永远诚实 FAILED
     影响: "AI 公司"空转; 解决方案: 接 DEEPSEEK_API_KEY 或 Provider 持久化 (S10-021)
  2. API 无认证 — FastAPI 裸奔 (仅本机监听)
     影响: 暴露即被任意调用; 解决方案: 加 token/认证 或 明确仅 localhost

P1:
  1. Task 双系统 (backlog task vs exec Task T-001) — 执行链断裂
     影响: UI 创建的 backlog task 无法直接执行; 解决方案: 统一 Task id 或映射
  2. Agent 双模型 (org Employee vs exec Agent) — resolve_agent_skills 靠系统映射
     影响: hack 味; 解决方案: 单 Agent 模型
  3. service.py 膨胀 (4046 行) / domain.ts 膨胀 (1391 行)
     影响: 维护成本; 解决方案: 拆包
  4. 3 个 CLI 入口分裂 + bin/factory project/run stub
     影响: 用户困惑, 承诺未兑现; 解决方案: 统一命令树
  5. 前端旧页面 (Intelligence/Review/Approval) 仍是 S9 模式
     影响: 风格不一致; 解决方案: 迁移 Af 模式

P2:
  1. 包名含连字符 (factory-console) → importlib 样板
  2. 仓库根未跟踪中文 md (商业评测-v1.md 等) — 应清理或移 docs/
  3. CLI 无专项测试
  4. pytest 偶发失败 (test_cli_runtime_test smoke 全量跑时偶发, 单跑恒过)
```

# 13. Next Development Plan

```
P0: LLM Activation (S10-021 建议)
    - Provider Config: 持久化 (providers.json) + key 接入
    - Model Config: Model Catalog (名称/能力/context/cost)
    - Real Execution: AgentRuntime 连接真实 Provider → execute 真正跑起来

P1: 真实软件生产闭环
    - execute → artifact → quality gate 全链
    - Task 单系统统一 (backlog ↔ exec)
    - 前端执行触发 (从 UI 下发任务执行)

P2: 治理增强
    - API 认证 / 策略引擎 / RBAC
    - LLM Router (能力/成本/延迟/故障切换)
    - Multi Agent 编排 (基于 Skill/Tool 链)
    - Memory (Experience 雏形 → 跨会话) + Learning Loop
```

# 14. AI Agent Handoff Notes ⭐ (最重要)

```
给下一位 AI Agent 的核心指令:

1. 当前项目不要重新设计, 不要推翻已有架构。
   架构决策已确定 (见下), 你要做的是沿路线推进, 不是重构。

2. 正确路线 (已确认, 不要改变顺序):
   Identity → Runtime → Execution Loop → Tool → Skill → MCP
   → Real Execution → Governance → Multi Agent → Memory → Learning
   (当前在 MCP 完成, 下一步是 Real Execution = LLM Activation)

3. 已确定的设计决策 (不要改):
   - Tool 纯内部模型 (不绑 OpenAI/MCP/第三方协议) — S10-018
   - MCP 是 Tool Runtime 外部扩展, 不绕过治理 — S10-020
   - 权限链 3 环: Agent has Skill → Skill includes Tool → Tool Permission — S10-019
   - 事件溯源 SQLite 是唯一事实源 — S10-012
   - 诚实原则: 无数据 → Unavailable; 无 LLM key → 诚实 FAILED (不伪造)
   - 四层架构: Core (冻结) → Extension → Intelligence → Console
   - 前端真实数据铁律: UI→Adapter→API→真实 Domain 闭环, 禁 mock 冒充
   - 每 Task 独立 commit + push + completion 文档 + 停下等审核

4. 环境事实:
   - 后端: FastAPI 8011 (启动命令见下), 数据根 ~/.factory/
   - 前端: Vite dev server (proxy /api → 8011)
   - 测试: pytest 7775 / vitest 669 / tsc 0 (全量跑 ~3 分钟)
   - Telegram gateway 运行中 (launchd, 手机可控制)
   - 8011 重启命令:
     cd /Users/Shared/work/ai-software-factory/factory-console/web
     PYTHONPATH=/Users/Shared/work/ai-software-factory/factory-core:/Users/Shared/work/ai-software-factory/factory-org:/Users/Shared/work/ai-software-factory/factory-exec
     ../../.venv/bin/python -c "import sys; sys.path.insert(0,'backend'); import uvicorn; from fastapi_adapter import create_app; uvicorn.run(create_app(), host='127.0.0.1', port=8011)"

5. 角色边界 (用户铁律):
   - Hermes = Orchestrator/CTO, 不直接改源码 — 实现通过 Sub-agent (delegate_task)
   - Sub-agent 常被工具上限截断 → Orchestrator 接手收尾是常态
   - 禁止: rm/删除/临时脚本/git push -f; 后端 47.113.187.93 禁改删重启
   - 用户拒绝 占位 UI / 假入口 / mock 冒充
```

# 15. Quick Start For New Agent

```
接手步骤:

1. 读本文件 (docs/project-state/AI_FACTORY_CURRENT_STATE.md)
   30 秒理解项目全貌。

2. 读最新 Sprint completion:
   docs/sprint10/S10-020-task001-completion.md (MCP, 最新)
   docs/sprint10/S10-019-task001-completion.md (Skill)
   docs/sprint10/S10-018-task001-completion.md (Tool)
   以及 docs/audit/AI-FACTORY-CURRENT-STATE-REVIEW.md (全量技术审查)

3. 检查 git 状态:
   cd /Users/Shared/work/ai-software-factory && git status
   git log --oneline -10
   (确认 HEAD 与工作区; 注意仓库根中文 md 是垃圾文件勿提交)

4. 跑测试确认基线:
   .venv/bin/python -m pytest -q          (7775, ~3 分钟)
   cd factory-console/web/frontend && npx vitest run && npx tsc --noEmit

5. 确认后端活:
   curl http://127.0.0.1:8011/api/projects  (应 200)
   若 8011 死 → 按 §14 命令重启

6. 下一步任务 (如果用户没给新指令):
   等用户指令。用户说"继续" → S10-021 LLM Activation
   (Provider 持久化 + Model Catalog + 真实执行)
```

---

> 快照完成 | 基于 git 7ea7bd4 + 最新测试 (pytest 7775 / vitest 669 / tsc 0) + 真实 API/CLI/数据扫描
> 只提交文档, 未修改代码
