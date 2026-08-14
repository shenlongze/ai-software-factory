# S10-027 Task 1 — Architecture Boundary Audit

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只读审计,未修改代码
> 目标:分析模块边界,评估独立产品化可能

---

## 1. 模块全景(含 evaluation/memory 现状)

```
AI Software Factory (v0.1, tag v1.0.0-rc1)
├── factory-core/        Core 冻结层: events/tasks/agents/workflows/providers/validation/metrics
├── factory-console/     Console 层: CLI (cli_factory/doctor/services) + LLM 基础设施 (llm_control/model_catalog/llm_router/agent_policy) + FastAPI + React
├── factory-exec/        Execution: agent_runtime/execution_loop/tool/skill/mcp/沙箱
├── factory-org/         Organization: company/employee/artifact/approval/workflow
├── factory-runtime/     沙箱执行环境
└── evaluation / memory  无独立目录 (能力分散在 exec 的 evaluator/experience, 见下)
```

## 2. 各模块边界分析

### 2.1 factory-core

| 维度 | 分析 |
|---|---|
| 职责 | 领域模型 + 事件溯源(SQLite)+ 冻结基线(Core 零修改铁律) |
| 输入 | 领域操作命令 |
| 输出 | 事件/模型对象 |
| 依赖方向 | 零领域依赖(最底层) |
| 耦合点 | 无(设计上就是最稳定层) |
| 独立产品化 | 不适合独立(基础设施层,无独立价值) |

### 2.2 factory-console(核心资产)

| 维度 | 分析 |
|---|---|
| 职责 | ① CLI 产品入口 ② LLM 基础设施(ControlPlane/ModelCatalog/Router/AgentPolicy)③ 后端 API + 前端 |
| 输入 | 用户命令 / HTTP / 配置文件 |
| 输出 | 决策(ModelChoice)/ 配置 / API 响应 |
| 依赖方向 | → factory-core(事件)/ factory-exec(延迟 import)/ factory-org(装配) |
| 耦合点 | **① LLM 基础设施与 CLI 同包**(llm_control/router 在 console 包内,独立产品化需拆包)② service.py 大装配(3000+ 行) |
| 独立产品化 | **高**(Router/ControlPlane 最易独立) |

### 2.3 factory-exec(执行引擎)

| 维度 | 分析 |
|---|---|
| 职责 | AgentRuntime / ExecutionLoop / Tool / Skill / MCP / 沙箱 / evaluator / experience |
| 输入 | ExecutionRequest + provider |
| 输出 | ExecutionResult / Artifact |
| 依赖方向 | 只 import 同层 + stdlib(Removal Isolation) |
| 耦合点 | **provider 装配在 console 层**(workflow_runner._build_provider)——职责倒挂,exec 无法独立运行 |
| 独立产品化 | **中**(Agent Execution Engine;需先解决装配倒挂) |

### 2.4 providers(factory-core/providers)

| 维度 | 分析 |
|---|---|
| 职责 | Provider 目录/usage 统计/feedback/capability 画像/selector(四层链) |
| 现状 | **与执行链未接线**(S10-021~024 走 console 层新模块;core providers 是 Phase 8A/8B 遗留) |
| 耦合点 | **双轨**:core providers vs console llm_control 并存 |
| 独立产品化 | 中(usage/feedback 数据基础;但需先统一) |

### 2.5 router(llm_router.py)

| 维度 | 分析 |
|---|---|
| 职责 | 五层决策链 → ModelChoice |
| 输入 | task_type/agent/skill/project/explicit + ControlPlane + ModelCatalog |
| 输出 | ModelChoice {model_id, provider_id, score, reasons, source} |
| 依赖方向 | → llm_control / model_catalog / agent_policy(同 console 包) |
| 耦合点 | **ModelChoice 定义在 model_catalog.py**(应独立共享类型) |
| 独立产品化 | **最高**(AI Decision Router) |

### 2.6 agent

| 维度 | 分析 |
|---|---|
| 职责 | Agent 注册/技能绑定/生命周期(org Employee + exec Agent 双模型) |
| 输入 | agent.yaml / agents.json |
| 输出 | Agent 对象 / 执行身份 |
| 耦合点 | **双模型 hack**(org Employee vs exec Agent 系统映射);provider 装配依赖 console |
| 独立产品化 | **中高**(Agent Management Platform;先解双模型) |

### 2.7 skill

| 维度 | 分析 |
|---|---|
| 职责 | Skill 注册/权限链(Agent→Skill→Tool 3 环)/MCP 适配 |
| 输入 | skill.yaml / SkillRegistry |
| 输出 | Skill 对象 / 权限决策 |
| 耦合点 | 权限链硬编码 SYSTEM_AGENT_SKILLS(策略引擎缺失) |
| 独立产品化 | **中高**(Skill 市场/Registry) |

### 2.8 rag

| 维度 | 分析 |
|---|---|
| 职责 | 未实现(CLI 占位 "RAG 未实现 — 规划中") |
| 耦合点 | 无(空白) |
| 独立产品化 | 中(Enterprise Knowledge;需先实现) |

### 2.9 governance(org 审批/审计)

| 维度 | 分析 |
|---|---|
| 职责 | 审批门/权限链/事件审计(org + events) |
| 输入 | approval 请求/权限检查 |
| 输出 | 审批决定/审计事件 |
| 耦合点 | 与 console service workflow_lifecycle 装配耦合;审计浏览器缺失 |
| 独立产品化 | **中高**(AI Governance OS) |

### 2.10 evaluation(分散)

| 维度 | 分析 |
|---|---|
| 现状 | exec 层有 evaluator.py/candidate.py(候选评估);无独立 evaluation 模块 |
| 独立产品化 | **中**(Evaluation Platform;需先整合) |

### 2.11 memory(雏形)

| 维度 | 分析 |
|---|---|
| 现状 | exec 层 experience.py/experience_ctx.py(经验提取雏形);无跨会话 Memory |
| 独立产品化 | 低(未成熟) |

## 3. 依赖方向总览

```
CLI (cli_factory/doctor/services)
  │
  ├──▶ LLM Router ──▶ ControlPlane ──▶ providers.json
  │        │              │
  │        ▼              ▼
  │    ModelCatalog ── AgentPolicy (yaml)
  │
  ├──▶ workflow_runner ──▶ factory-exec (runtime, 延迟 import)
  │
  └──▶ service ──▶ factory-org / factory-core (装配)
```

## 4. 独立产品化评估矩阵

| 模块 | 独立产品 | 市场价值 | 技术壁垒 | 当前完成度 | 商业化可能 |
|---|---|---|---|---|---|
| Router | AI Decision Router | 高 | 中(决策链+可解释) | 80% | 高(SDK/服务) |
| Governance | AI Governance OS | 中高 | 中(审批/审计) | 50% | 高(企业合规) |
| RAG | Enterprise Knowledge | 中 | 低(竞争激烈) | 0% | 中 |
| Agent Lifecycle | Agent Management | 中高 | 中(治理差异化) | 60% | 中高 |
| Evaluation | Evaluation Platform | 中 | 中 | 30% | 中 |
| Skill | Skill Registry/市场 | 中高 | 中(权限链) | 60% | 中高 |
| Memory | 经验/记忆服务 | 低(未成熟) | 高 | 10% | 低 |

## 5. 关键耦合点(产品化前置)

1. **ModelChoice 归属**:定义在 model_catalog,被 router 复用 → 应提升为共享类型
2. **provider 装配倒挂**:exec 依赖 console workflow_runner 装配 → 装配应下沉 exec
3. **双轨 Provider**:core providers(Phase 8A)vs console llm_control(S10-021)并存
4. **Agent 双模型**:org Employee vs exec Agent 系统映射 hack
5. **审计双轨**:exec usage vs core UsageStore;session 事件 vs org.execution

---

> 审计完毕 | 只读 | 独立产品化排序:Router > Governance/Agent > Skill > Evaluation > RAG
