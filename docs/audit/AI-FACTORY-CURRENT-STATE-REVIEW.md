# AI SOFTWARE FACTORY — FULL PROJECT TECHNICAL REVIEW & SUMMARY

> 日期: 2026-08-13 | 审查人: Hermes (CTO + Principal Engineer + AI Infrastructure Architect)
> 范围: 全量真实代码审查 — 基于 git log (ca93a55, 400+ commits)、真实测试结果 (pytest 7775 / vitest 669 / tsc 0)、真实 API (75+ 端点)、真实 CLI (3 个入口)、真实数据 (~/.factory)
> 性质: 非宣传总结。不美化。指出问题。

---

# 1. Executive Summary

## 当前项目是什么？

**AI Software Factory** 是一个"AI 软件公司操作系统" — 目标不是做一个 Agent Framework / Chatbot / Workflow Engine, 而是构建一个**治理驱动的 AI 软件生产系统**: 以"公司/部门/员工/项目/工作流"为组织隐喻, AI Employee 在 Governance + Audit + Permission 约束下执行软件开发任务。

## 解决什么问题？

- **人机协作生产**: 人类 (CEO/产品负责人) 定义项目与决策; AI 员工执行任务; 人工审批门控制风险
- **可观测的生产过程**: Runtime Session / Event Chain / Timeline / Dashboard 让人类能看到"AI 公司在干什么"
- **治理**: Agent→Skill→Tool→Permission 四层权限链, 事件溯源审计 (Who/What/When)

## 当前技术阶段

```
S10-016 (Runtime Foundation)      ✅ 完成
S10-017 (Execution Loop)          ✅ 完成
S10-018 (Tool Runtime)            ✅ 完成
S10-019 (Skill System)            ✅ 完成
S10-020 (MCP Adapter)             ✅ 完成
S10-014/015 (Frontend Console)    ✅ 完成 (17 页面 + 21 Af 组件)
Multi Agent / Memory / Learning   ⬜ 未开始 (路线图后段)
```

## 已达成能力 (真实证据)

| 能力 | 证据 |
|---|---|
| Runtime Session 生命周期 | 5 态状态机 + 9 事件类型 → 真实 curl 联调 (rs-3fb653f1) |
| Execution Loop | CREATED→RUNNING→WAITING_*→COMPLETED|FAILED, AgentStep 6 类型 |
| Tool Runtime | filesystem.read 沙箱 (穿越/编码/symlink 防护) + 403 权限实测 |
| Skill System | 3 内置 Skill + Agent→Skill→Tool 权限链 (backend-1 实测) |
| MCP Adapter | Mock echo 工具全链路 (连接→发现→注册→执行) |
| 前端 Console | 17 页面真实数据源 (vite proxy → 8011), 非 mock |
| 测试 | pytest 7775 / vitest 669 / tsc 0 / build ✓ |

## 评级 (诚实)

```
Architecture maturity rating:  6.5 / 10  (分层清晰, 但 Provider 路由/治理策略未落地)
Agent maturity rating:         4.5 / 10  (执行骨架完整, 但无真实 LLM 驱动 — 关键短板)
Production readiness rating:   3.5 / 10  (无真实执行闭环, 无 CI/CD, 无部署)
```

---

# 2. Product Vision Alignment

## 符合目标的部分

```
✅ 组织隐喻: Company/Department/Employee/Project/Workflow — 是"操作系统"不是"聊天"
✅ 治理优先: Agent→Skill→Tool→Permission 链, MCP 不绕过 (S10-020 核心原则)
✅ 可观测: Dashboard/Quality Gate/Runtime Timeline 完整
✅ 人机决策: Approval Gate (APR-001 真实审批门), Human Decision 闭环
✅ 事件溯源: Audit 记录 Who/What/When
```

## 偏离的部分

```
⚠️ 核心执行仍是骨架: AgentRuntime.execute() 存在但无 LLM key 驱动
   (项目无 .env; Hermes .env 的 DeepSeek key 未接入项目) — "AI 公司"
   目前是"空转的工厂", 不是"生产中的工厂"
⚠️ Frontend 与 Backend Domain 有映射断层: Console 是 S9 Human Console 演进,
   部分页面 (Intelligence/Review/Approval) 仍是旧模式, 与新的
   Runtime/Skill/Tool/MCP 域不完全对齐
```

## 退化风险

```
风险 1: 退化为 "Workflow Engine" — 若继续扩展 Workflow/Stage 而无真实执行,
        会变成另一个流程编排器 (市场已饱和)
风险 2: 退化为 "Agent Framework" — 若急于做 Multi Agent 编排而无执行基础,
        会变成又一个 LangGraph 竞品 (用户已明确拒绝此方向)
风险 3: 前端膨胀 — 17 页面 + 21 组件, 若无真实数据驱动, 会变成"演示壳"
```

---

# 3. Overall Architecture Review

```
┌─────────────────────────────────────────────────────┐
│  Governance Layer (治理层)                            │
│  Permission Chain: Agent→Skill→Tool→MCP (Default Deny)│
│  Approval Gate / Human Decision / Review Feedback     │
├─────────────────────────────────────────────────────┤
│  Audit Layer (审计层)                                 │
│  Event Sourcing (SQLite) — org.* / workflow.* /       │
│  runtime_session.* / tool.* / skill.* / mcp.*         │
│  Who/What/When/Model/Tool/Result                      │
├─────────────────────────────────────────────────────┤
│  Execution Layer (执行层) — factory-exec               │
│  AgentExecutor → ExecutionLoop → Planner → Skill →    │
│  ToolExecutor → MCP Adapter → AgentRuntime → LLM       │
├─────────────────────────────────────────────────────┤
│  Domain Layer (域层) — factory-core / factory-org      │
│  Task / Project / Agent / Workflow / Artifact /        │
│  Approval / Capability / Experience                    │
├─────────────────────────────────────────────────────┤
│  Console Layer (接口层) — factory-console              │
│  FastAPI (75+ 端点) + CLI (bin/factory + org/exec CLI) │
├─────────────────────────────────────────────────────┤
│  Frontend Layer (展示层) — React 18 + Vite            │
│  Dashboard / Project Shell / Todo Tree / Runtime /     │
│  Quality Gate / Adapter (domain.ts 真实转换)           │
├─────────────────────────────────────────────────────┤
│  Data Layer (数据层)                                   │
│  ~/.factory/ (SQLite events + JSON stores)            │
│  org/ projects/ tasks/ agents/ runtimes/ sessions/     │
└─────────────────────────────────────────────────────┘
```

**层职责**: 每层职责清晰, 依赖单向 (Frontend→Console→Domain→Data)。这是当前最大的架构资产。

---

# 4. Repository Structure Review

```
/Users/Shared/work/ai-software-factory/
├── factory-core/         # 核心域: agents/tasks/projects/workflow/events (~30K 行)
├── factory-org/          # 组织域: company/employee/authority/artifact/approval
├── factory-exec/         # 执行域: agent_runtime/execution_loop/tool/skill/mcp/provider
├── factory-runtime/      # 沙箱执行环境
├── factory-console/      # FastAPI + service.py (900 行核心) + cli_factory + workflow_runner
│   └── web/frontend/     # React 18 + Vite (src/ 25K 行)
├── tests/                # 332 pytest 文件 (7775 测试)
├── docs/sprint10/        # 每个 Task 的 completion 报告 (审计链完整)
├── docs/design/          # 架构设计 (AF-UI-Architecture / plan)
└── bin/factory           # CLI 薄包装
```

**结构问题**:

```
P1: factory-console/service.py 已膨胀 (4046 行) — 所有 domain 方法的失败安全
    装配逻辑堆在单文件, 未来应拆 service/ 包
P1: 包名含连字符 (factory-console) → 需要 importlib 加载, 增加测试/导入复杂度
    (tests/console 所有文件都有 sys.path 注入 + importlib 样板)
P2: 前端 17 页面 + 21 组件但无清晰分层目录 (components/af 全平铺)
P2: 大量未跟踪中文 md 文件在仓库根 (CLI命令参考文档.md 等) — 应清理或移 docs/
```

---

# 5. Completed Feature Inventory

| Feature | Status | Implementation Location | Architecture Role | Test Evidence |
|---|---|---|---|---|
| Workspace Shell | ✅ | frontend/src/components/af/AfWorkspaceShell.tsx | 三栏壳 + 7 导航 | 434 tests 基线 |
| Project Shell | ✅ | AfProjectShell.tsx | 11 导航 + 子页分发 | 449 tests |
| Todo Tree | ✅ | AfTodoTree.tsx + AfTodoTreePage.tsx | Project Execution Center | 561 tests, 真实 backlog |
| Task Detail Panel | ✅ | AfTaskDetailPanel.tsx | Task→Workflow→Runtime 闭环 | 608 tests |
| Workflow Viewer | ✅ | AfWorkflowViewer.tsx | Instance/Template/Timeline 三层 | 580 tests |
| Runtime Timeline | ✅ | AfRuntimeTimeline.tsx + AfRuntimePage.tsx | 8 项展示 + 失败原因 | 608 tests |
| Dashboard | ✅ | AfDashboard.tsx | 6 模块 Control Center | 636 tests |
| Quality Gate | ✅ | AfQualityGate.tsx | 5 模块 + 诚实 Unavailable | 659 tests |
| Runtime Session | ✅ | exec/runtime_session.py | 5 态状态机 + 事件 | 51 tests + curl |
| Agent Executor | ✅ | exec/agent_executor.py | Task→Session→LLM→Result | 12 tests + curl |
| Execution Loop | ✅ | exec/execution_loop.py (878 行) | Reason→Act→Observe→Complete | 39 tests |
| Tool Runtime | ✅ | exec/tool.py + tools/filesystem.py | 原子能力 + 沙箱 | 35 tests + curl |
| Skill System | ✅ | exec/skill.py | 职业能力组合 + 权限链 | 28 tests + curl |
| MCP Adapter | ✅ | exec/mcp.py | 外部工具接入 (Mock) | 30 tests + curl |
| CLI | ⚠️ 部分 | bin/factory + org/exec CLI | 管理入口 | 无 CLI 专项测试 |
| Frontend Console | ✅ | 17 页面 + 21 组件 | 人类控制面 | 669 vitest |

---

# 6. Module Deep Review

## 6.1 Core — Workspace / Project / Task

**Purpose**: 项目生命周期 (idea→discovery→confirm→backlog→sprints→milestones→roadmap)
**Implementation**: factory-org/org/projects.py + management.py; POST /api/projects 创建 + backlog 4 平行数组 (epics/features/stories/tasks)
**Strength**: 真实数据结构完整 (4 平行数组 + children id 引用反向索引); 状态机 6 态 (todo→ready→in_progress→blocked→review→done)
**Weakness**: Task 与 Exec TaskStore (Core) 是**两套系统** (backlog task vs execution task T-001) — 执行时 Task 校验找不到 backlog task (curl 实测 TASK-425bf30b → "task not found")
**Improvement**: 统一 Task 标识 (backlog task_id → execution task_id 映射), 或 Executor 支持 backlog task 直接执行

## 6.2 Agent — Model / Executor / Execution Loop / Planner

**Purpose**: Agent 身份 + 执行编排
**Implementation**: agents/registry.py (Agent.skills) + agent_executor.py (170 行) + execution_loop.py (878 行) + LLMPlanner (provider.py 复用)
**Strength**: ExecutionLoop 是真正亮点 — 完整状态机 (6 态) + AgentStep 6 类型 + 事件链 (23 类型) + MAX_ROUNDS 防循环 + 条件触发事件 (skill/mcp 不污染既有链)
**Weakness**: Agent 模型分裂 — org Agent (role_ids) vs exec Agent (T-001 等), resolve_agent_skills 用系统映射兜底 (有 hack 味); LLMPlanner 无 LLM key 时诚实 FINAL (单轮空转)
**Improvement**: Agent 单模型 + LLM 路由接入 (见 §9/§10)

## 6.3 Runtime — Session / State / Event

**Purpose**: 一次 AI 执行的生命周期记录
**Implementation**: runtime_session.py (480 行) — RuntimeSession 5 态 + RuntimeEvent 23 类型 + AgentStep + add_step + 原子写 Store
**Strength**: 状态机严谨 (非法转换响亮); 事件 9→14→18→20→23 全部向后兼容; 输出字段 (execution_output/summary/raw_response) 为 Artifact 层预留
**Weakness**: Session 状态 (PENDING/RUNNING/SUCCESS/FAILED) 与 Loop 状态 (CREATED/RUNNING/WAITING_*) 是两套 — 映射关系隐式
**Improvement**: 定义明确的 Session↔Loop 状态映射表 (文档化)

## 6.4 Capability — Tool / Skill / MCP

**Purpose**: AI 员工的能力体系
**Implementation**: tool.py (397) + skill.py (420) + mcp.py (442)
**Strength**: 设计优雅 — Tool 纯内部模型 (不绑 OpenAI/MCP) + Skill 组合 + MCP Adapter 转换; 权限链 3 环 (Agent has Skill→Skill includes Tool→Tool Permission) 清晰; MCP 不绕过治理是正确决策
**Weakness**: 只有 filesystem.read 一个真实 Tool; MockMCP echo 是演示; Skill 只是组合+约束 (无技能差异化行为)
**Improvement**: 第二/第三个真实 Tool (search/execute_command/写文件); Skill 加 instructions 差异化 (当前 instructions 存在但未真正影响 Planner)

## 6.5 Frontend — Console / Adapter / Types

**Purpose**: 人类控制面
**Implementation**: 17 页面 + 21 Af 组件 + domain.ts (1379 行 Adapter 全真实转换) + 669 vitest
**Strength**: 真实数据铁律执行到位 — vite proxy → 8011, 无 mock 冒充; 四态 (Loading/Success/Empty/Error) 组件; 诚实 Unavailable (无数据不编造); §6.3 message 优先降级
**Weakness**: domain.ts 单文件膨胀 (1379 行); Af 组件全平铺; 部分页面 (Intelligence/Review) 仍是旧 S9 模式
**Improvement**: domain.ts 拆分; 旧页面迁移到 Af 模式

## 6.6 CLI

**Purpose**: 管理入口
**Implementation**: bin/factory (start/stop/status + init/config/project/run stubs) + org CLI (company/employee/artifact/workflow/approval/project) + exec CLI (run/status/providers/approval)
**Weakness**: bin/factory 的 project/run 是**预留 stub 未实现**; 无 CLI 专项测试; 3 个 CLI 入口分裂 (bin/factory vs .venv/bin/factory vs exec cli)
**Improvement**: 统一 CLI 命令树 + CLI 测试

---

# 7. CLI 完整性审查

## Command Inventory

| 入口 | command | status | implementation | API dependency |
|---|---|---|---|---|
| bin/factory | start | ✅ 实现 | cli_factory.py start | 起后端+前端 |
| bin/factory | stop | ✅ 实现 | cli_factory.py stop | 杀进程 |
| bin/factory | status | ✅ 实现 | cli_factory.py status | 8011 探测 |
| bin/factory | init/config/project/run | ⚠️ stub | STUB_COMMANDS | 未实现 |
| org CLI | company/employee/authority/knowledge/artifact/workflow/approval/project | ✅ 实现 | factory-org/org/cli.py | org 事件 API |
| exec CLI | run/status/providers/approval | ✅ 实现 | factory-exec/exec/cli.py | exec API |

## Command Validation (真实)

```
✅ ./bin/factory start — 已验证可起服务 (8011 + 前端 5199)
✅ ./bin/factory status — 已验证 (端口/进程/数据目录)
⚠️ bin/factory project/run — 未实现 (stub) — 用户"项目管理/执行"必须走前端或 org CLI
❌ 无 CLI 自动化测试 (pytest 覆盖 org CLI 事件但无 bin/factory 端到端)
```

---

# 8. API Review

**方法/路径/用途**: 见 §3 清单 (75+ 端点, 9 个 POST /api/projects/* backlog CRUD, 8 个 runtime-session, 3 个 tool, 2 个 skill, 3 个 mcp)

| 维度 | 状态 |
|---|---|
| 完整性 | ✅ backlog/sprints/milestones/roadmap/approvals/artifacts/workflow/runtimes/sessions/tools/skills/mcp/dashboard 全覆盖 |
| 一致性 | ✅ 错误映射统一 (ValueError→400, None→404, 权限→403); 写路径白名单测试 (test_console_web_adapter) 防泄漏 |
| 缺失 | ⚠️ 无 /api/agents/{id}/execute (执行入口只有 /api/runtime/execute 接受 task_id+agent_id); 无 artifact 创建 API (executor 输出→artifact 断链); 无 model/provider 路由 API |

---

# 9. Provider + Model Management Review ⭐

## 当前实现 (真实)

```
ProviderRegistry (provider.py): register/get — 纯内存注册表
ProviderConfigChecker: key 预检 (configured=True 仅表示 key 存在)
ProviderConfigStatus: provider_id/display/key_var/configured
AgentRuntime.execute(): LLMPlanner → provider.generate() → ProviderResponse
```

## 真实状态

```
❌ 项目无 .env — 后端 8011 无 LLM key
❌ 无 Model 抽象: 只有 provider_id, 无 model 名称/能力/上下文/成本元数据
❌ 无 Provider 路由: execute 用单一 provider (self._provider()), 无选择逻辑
❌ ProviderRegistry 无持久化 (重启丢失)
⚠️ Hermes .env 有 DEEPSEEK_API_KEY 但未接入项目
```

## 缺少 (关键)

```
1. Model 注册表: {model_id, provider, capability (coding/reasoning/chat), context_window, cost, availability}
2. Provider 持久化: 配置存 ~/.factory/providers.json (已有目录但空)
3. Provider 连接: 从配置加载真实 Provider 到 AgentRuntime (当前每次手工 new)
```

## 未来演进

```
config → ProviderRegistry (持久化) → Model Catalog → 按任务选 model → 执行
```

---

# 10. Intelligent LLM Routing Review ⭐

## 当前状态 (真实)

```
❌ 无路由: execute → self._provider() 单一 provider (通常 None → 诚实 FAILED)
❌ 无能力路由/成本路由/延迟路由/故障切换/负载均衡
✅ 唯一"路由"是 LLMPlanner 无 Provider 时诚实 FINAL 回退 (降级路径正确)
```

## 未来设计

```
Task → LLM Router → Model Selection → Provider → Execution
  Capability Routing:  coding→deepseek-coder / reasoning→claude / simple→本地 qwen
  Cost Routing:       默认 cheap model, 复杂任务升级
  Latency Routing:    交互场景选 fast, 批处理选 cheap
  Failover Routing:   provider A 失败 → provider B (响应错误自动切换)
  Load Balancing:     多 key 轮转 (Hermes credential pool 模式)
```

**关键缺口**: 这是用户 memory 中明确的方向 ("providers=可解释LLM路由最先开源"), 但 S10-020 仍未启动。

---

# 11. Internal Governance Implementation Review ⭐

## 已落地 (真实)

```
✅ Identity Governance: User (ALLOWED_USERS) / Project / Agent (registry) / Role (role_ids)
✅ Permission Governance: Agent→Skill→Tool 3 环权限链 (check_tool_access)
   - 实测: backend-1→filesystem.read ✅; flutter-dev→403; ghost→403
   - Skill 环: Skill 不含 tool → 拒绝; MCP 工具同链 (不绕过)
✅ Execution Governance: Approval Gate (APR-001 真实审批门, prd gate)
   - Human Decision 闭环 (Quality Gate WAITING_FOR_REVIEW)
✅ Policy: 最小权限表 (backend-1 白名单); ToolPermissionPolicy (allow_all/收窄)
✅ Audit: 事件溯源 SQLite — org.*/workflow.*/runtime.*/tool.*/skill.*/mcp.*
   - AuditStore.append 含 capability 字段 {agent/skill/mcp/llm: {id, version}}
   - console.viewed 审计 (谁看了什么)
```

## 缺失

```
❌ 无策略引擎 (规则动态配置): 权限是硬编码 (SYSTEM_AGENT_SKILLS), 非可配置策略
❌ 无角色→权限声明文件 (RBAC 策略未独立)
❌ 审批门覆盖窄: 只有 prd gate 自动请求; 无代码变更审批门 (execution approval 存在但未连 Quality Gate)
❌ Audit 无查询 API: 有记录但前端无统一审计浏览器
```

---

# 12. Compliance Review ⭐

| 维度 | 现状 | 差距 |
|---|---|---|
| Data Governance | ✅ Project Boundary 存在 (~/.factory/org/{project}) | ❌ 无项目级数据隔离测试; 跨项目访问未验证 |
| Privacy | ⚠️ filesystem.read 沙箱限 workspace root | ❌ 无 LLM 数据发送控制 (发送内容未审计/未可配置脱敏) |
| Audit Compliance | ✅ 事件溯源完整 | ❌ 无合规查询/导出; 无审计保留策略 |
| Security | ✅ Tool sandbox + 权限链 + Secret 管理 (env) | ❌ 无 secret 扫描 (GitHub 私库但无 gitleaks); API 无认证 (FastAPI 裸奔, 仅本机); MCP 仅 Mock 无真实传输安全 |

**企业级差距**: API 无认证是最大问题 — 若暴露到局域网/公网, 任何进程可调 POST /api/runtime/execute。

---

# 13. Execution Flow Analysis

```
User Request (前端/CLI)
  ↓ Task (backlog 或 exec T-001)
  ↓ Agent Selection (手工指定 agent_id — 无自动分配)
  ↓ Skill Loading (skill_loaded 事件, 条件触发)
  ↓ Planner (LLMPlanner — 无 LLM key → 诚实 FINAL)
  ↓ LLM Decision (decision_created 事件)
  ↓ Tool/MCP (tool_requested→tool_started→tool_completed; MCP echo 可执行)
  ↓ Observation (observation_received)
  ↓ Result (execution_completed|failed + output/summary/raw_response)
  ↓ Audit (全事件入 SQLite)
```

**缺失 (明确)**:
```
❌ Memory — 无跨会话上下文 (Experience 有雏形但未连执行)
❌ Learning — 无失败→改进循环 (execution_failed 后无自动学习)
❌ Feedback — 无执行结果反馈闭环 (Review 存在但未连 Quality Gate)
```

---

# 14. Data Model Review

```
Agent ──1:N── Skill (Agent.skills / SYSTEM_AGENT_SKILLS)
Skill ──1:N── Tool (Skill.tools 引用)
Tool ──1:1── MCPToolAdapter (source=mcp)
Agent ──1:N── RuntimeSession (agent_id)
Task ──1:N── RuntimeSession (task_id)
RuntimeSession ──1:N── RuntimeEvent (session_id)
RuntimeSession ──1:N── AgentStep (session_id)
Project ──1:N── Backlog (4 平行数组)
Project ──1:N── Workflow Instance
Approval ──1:1── Artifact (approval.artifact_id)
```

**扩展风险**:
```
P1: Task 双系统 (backlog vs exec) — 关系断裂, 执行链无法从 UI Task 直达
P1: Agent 双模型 (org Employee vs exec Agent) — resolve_agent_skills 靠系统映射 hack
P2: 无 Model/Provider 实体 — LLM 路由无法建模
P2: 无 Memory 实体 — 未来接入需新 schema
```

---

# 15. Testing & Quality Review

```
pytest:  7775 passed (332 文件) — 每 Sprint 全量复跑, 零回归
vitest:  669 passed (56 文件)   — 含组件/Adapter/路由/四态
tsc:     0 error
build:   ✓ (319KB)
CI/CD:   ❌ 无 (全本地跑, 无 GitHub Actions)
```

**评价**:
```
✅ 测试质量高: TDD 流程严格执行 (每 Task RED→GREEN); 权限边界测试防写路由泄漏;
   事件链精确断言; 环境契约化 (api-live 不硬编码项目名)
✅ 测试数量递增记录清晰 (305→434→449→498→526→541→561→580→608→609→636→659→664→665→666→667→668→669)
⚠️ 偶发失败模式: test_cli_runtime_test smoke 全量跑时偶发 1 失败 (单跑恒过) — 时序问题
⚠️ CLI 无专项测试
❌ 无 CI — 唯一防线是"每 Task 人工审核"
```

---

# 16. Technical Debt

## P0 (必须尽快)

| 问题 | 原因 | 影响 | 解决方案 |
|---|---|---|---|
| 无 LLM key 接入 | 项目无 .env | 执行永远 FAILED — "AI 公司"空转 | 接 DEEPSEEK_API_KEY 或配置 Provider 持久化 |
| API 无认证 | FastAPI 裸奔 (仅本机) | 暴露即被任意调用 | 加 token/session 认证 (或明确仅 localhost) |

## P1

| 问题 | 原因 | 影响 | 解决方案 |
|---|---|---|---|
| Task 双系统 | backlog vs exec 独立演进 | 执行链断裂 | 统一 Task id 或映射 |
| Agent 双模型 | org vs exec | resolve_agent_skills hack | 单 Agent 模型 |
| service.py 膨胀 | 900+ 行单文件 | 维护成本 | 拆 service/ 包 |
| domain.ts 膨胀 | 1379 行单文件 | 维护成本 | 按域拆分 |
| 包名连字符 | 历史遗留 | importlib 样板 | 改名 (高风险, 暂缓) |

## P2

| 问题 | 原因 | 影响 | 解决方案 |
|---|---|---|---|
| 3 个 CLI 入口 | 独立演进 | 用户困惑 | 统一命令树 |
| bin/factory project/run stub | 未实现 | 承诺未兑现 | 实现或删除 |
| 前端旧页面 (Intelligence/Review) | S9 遗留 | 风格不一致 | 迁移 Af 模式 |
| 仓库根中文 md | 无纪律 | 污染 | 移 docs/ |
| CLI 无测试 | 未投入 | 回归风险 | 补 CLI 测试 |

---

# 17. Missing Features & Future Plan

| 特性 | 当前 | 设计方向 |
|---|---|---|
| Multi Agent | ❌ 未开始 | 基于现有 Skill/Tool 链: 多 Agent 共享工具 + 各自 Skill 门; 自动任务分配 (find_by_role 已有雏形) |
| Memory | ❌ 未开始 | Experience (已有雏形) → 跨会话记忆; 事件溯源可回溯 |
| Learning Loop | ❌ 未开始 | execution_failed → 原因分类 → 改进指令 → 重试 |
| Human Approval | ⚠️ 部分 | 审批门已存在 → 连 Quality Gate 全链 (代码变更门) |
| Workflow | ⚠️ 部分 | workflow 已有 → 接真实执行 (阶段级 Agent 执行) |

---

# 18. Roadmap

| Sprint | Goal | Value | Risk |
|---|---|---|---|
| S10-021 | Provider 配置持久化 + LLM key 接入 | 让执行真正跑起来 (最大价值) | 中 (Provider API 差异) |
| S10-022 | Model Catalog + 基础路由 (能力/成本) | 可解释模型选择 | 中 (路由策略设计) |
| S10-023 | Task 单系统统一 | 消除执行断链 | 高 (迁移风险) |
| S10-024 | 真实执行闭环 (execute→artifact→quality gate) | 第一个完整生产 | 高 |
| S10-025 | Multi Agent 编排 (基于 Skill) | "公司"形态 | 高 |
| S10-026 | Memory + Learning Loop | 自我改进 | 高 |
| S10-027 | 安全加固 (认证/CI/CD/secret 扫描) | 企业级 | 低 |

---

# 19. CTO Final Evaluation

## 如果这是创业项目

```
技术壁垒:
  ✅ 治理驱动架构 (Agent→Skill→Tool→Permission + 事件溯源) — 区别于 LangGraph/CrewAI
  ✅ 组织隐喻 (Company/Employee) — "AI 软件公司"而非"Agent 框架"
  ✅ 前端控制面完整 (人类可观察/决策)
  ⚠️ 但: 壁垒未成型 — 无真实执行, 竞争者 (Claude Code 团队模式/Cursor) 可快速复制骨架

优势:
  ✅ 架构决策正确 (复用 Provider、不绑 SDK、MCP 不绕过治理)
  ✅ 测试纪律强 (7775 测试, 每 Task 全量复跑)
  ✅ 用户 (你) 有 8 年 Java 后端 + 销售背景 — 产品化能力
  ✅ 模块化 (洋葱式开源 providers→intelligence→events) 可提知名度

风险:
  ❌ 最大风险: 停在"骨架" — 无 LLM key 接入的执行系统是空壳
  ❌ 市场风险: Agent 领域极热, 速度是关键
  ❌ 单一开发者: 单人 400+ commits, 精力分散 (前端+后端+架构)

结论: 值得继续投入, 但必须优先解决"真实执行" (S10-021 Provider 接入)。
      骨架期已 6 个 Sprint, 再拖 3 个 Sprint 无真实生产 → 建议重新评估。
```

---

# 20. Final Conclusion

## 当前 AI Factory 已经是

```
✅ 一个架构正确的 AI 软件生产系统骨架:
   - 治理层 (权限链/审批/审计) 完整
   - 执行层 (Session/Loop/Tool/Skill/MCP) 完整但无真实 LLM 驱动
   - 前端控制面完整 (17 页面, 真实数据)
   - 测试纪律优秀 (7775 pytest + 669 vitest)
```

## 还缺什么

```
1. ⭐ 真实 LLM 执行 (最大缺口 — Provider 持久化 + key 接入)
2. Model Catalog + LLM 路由 (能力/成本/故障切换)
3. Task/Agent 单系统统一 (消除断链)
4. Memory/Learning/Multi Agent (路线图后段)
5. 安全加固 (认证/CI)
```

## 下一阶段重点

```
S10-021: Provider 配置持久化 + LLM key 接入 — 让 "AI 公司" 真正开始生产。
         在此之前, 一切上层能力 (Multi Agent/Memory/Learning) 都是空中楼阁。

评分回顾: Architecture 6.5 / Agent 4.5 / Production 3.5
         最大短板 = 执行真实性。这是下一 Sprint 的第一优先级。
```

---

> 报告完成 | 基于真实代码 (ca93a55) + 真实测试 (pytest 7775 / vitest 669 / tsc 0) + 真实 API/CLI 扫描 + 真实数据 (~/.factory)
